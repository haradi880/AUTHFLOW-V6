"""
Main Routes - Home page, profiles, search, settings.
"""

import base64
import io
import secrets
from decimal import Decimal, InvalidOperation
from datetime import datetime

import qrcode
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import current_user, login_required, logout_user

from app.extensions import db
from app.models import User, Blog, Project, Category, Tag, Notification, Bookmark, Follow, Block, Report, DevLog, RoboticsProject, Job, LoginEvent, LoginSession, DonationIntent
from app.services.auth import issue_otp, normalize_email, validate_password_strength, verify_otp
from app.services.gamification import maybe_award_profile_completion
from app.services.security import revoke_all_sessions, revoke_other_sessions, revoke_session
from app.utils.audit import AuditEventType, audit_log, get_client_ip
from app.utils.rate_limit import rate_limit
from app.utils.helpers import format_datetime, paginate
from app.utils.uploads import save_upload, delete_file

# Create the blueprint
main_bp = Blueprint('main', __name__)


# ============================================================
# HOME PAGE
# ============================================================

@main_bp.route('/')
def home():
    """Home page - shows feed for logged in users, redirects visitors to blogs."""
    
    if current_user.is_authenticated:
        user_blog_query = Blog.query.filter_by(user_id=current_user.id)
        user_project_query = Project.query.filter_by(user_id=current_user.id)
        dashboard_stats = {
            "published_blogs": user_blog_query.filter_by(status="published").count(),
            "draft_blogs": user_blog_query.filter_by(status="draft").count(),
            "published_projects": user_project_query.filter_by(status="published").count(),
            "draft_projects": user_project_query.filter_by(status="draft").count(),
            "blog_views": db.session.query(db.func.coalesce(db.func.sum(Blog.views_count), 0))
            .filter_by(user_id=current_user.id)
            .scalar(),
            "blog_likes": db.session.query(db.func.coalesce(db.func.sum(Blog.likes_count), 0))
            .filter_by(user_id=current_user.id)
            .scalar(),
            "followers": current_user.followers_count(),
            "profile_views": current_user.profile_views_count or 0,
            "profile_completion": current_user.profile_completion(),
            "xp": current_user.xp_progress,
        }
        completion_tips = profile_completion_tips(current_user)
        user_drafts = user_blog_query.filter_by(status="draft").order_by(Blog.updated_at.desc()).limit(5).all()
        project_drafts = user_project_query.filter_by(status="draft").order_by(Project.updated_at.desc()).limit(5).all()

        # Get recent published blogs
        recent_blogs = Blog.query.filter_by(status='published')\
            .order_by(Blog.created_at.desc()).limit(6).all()
        
        # Get recent published projects
        recent_projects = Project.query.filter_by(status='published')\
            .order_by(Project.created_at.desc()).limit(6).all()
        
        # Get trending tags
        trending_tags = Tag.query.limit(10).all()
        following_ids = [follow.followed_id for follow in current_user.followed.limit(200).all()]
        following_blogs = []
        if following_ids:
            following_blogs = Blog.query.filter(Blog.user_id.in_(following_ids), Blog.status == 'published')\
                .order_by(Blog.created_at.desc()).limit(6).all()
        suggested_users = User.query.filter(User.id != current_user.id)\
            .order_by(User.created_at.desc()).limit(5).all()
        recently_viewed_ids = session.get("recently_viewed_blogs", [])
        recently_viewed = Blog.query.filter(Blog.id.in_(recently_viewed_ids), Blog.status == 'published').all() if recently_viewed_ids else []
        recent_devlogs = DevLog.query.filter_by(visibility='public')\
            .order_by(DevLog.is_pinned.desc(), DevLog.created_at.desc()).limit(5).all()
        
        # Get notifications count (unread)
        notification_count = 0
        if current_user.is_authenticated:
            notification_count = Notification.query.filter_by(
                user_id=current_user.id, 
                is_read=False
            ).count()
        
        return render_template('dashboard/home.html',
                             dashboard_stats=dashboard_stats,
                             completion_tips=completion_tips,
                             user_drafts=user_drafts,
                             project_drafts=project_drafts,
                             recent_blogs=recent_blogs,
                             recent_projects=recent_projects,
                             following_blogs=following_blogs,
                             suggested_users=suggested_users,
                             recently_viewed=recently_viewed,
                             recent_devlogs=recent_devlogs,
                             trending_tags=trending_tags,
                             notification_count=notification_count)
    
    # For visitors, show the blogs feed
    # FIXED: Changed 'main.blogs_feed' to 'blog.blogs_feed'
    return redirect(url_for('blog.blogs_feed'))


def profile_completion_tips(user):
    checks = [
        (user.full_name, "Add your full name."),
        (user.headline, "Add a headline that explains what you build."),
        (user.bio and len(user.bio) >= 40, "Write a short bio with at least 40 characters."),
        (user.location, "Add your location or remote availability."),
        (user.website, "Add your personal website."),
        (user.resume_url, "Add a resume or portfolio link."),
        (user.github, "Connect your GitHub profile."),
        (user.linkedin, "Connect your LinkedIn profile."),
        (len(user.get_skills_list()) >= 3, "Add at least three skills."),
        (user.avatar and user.avatar != "default.jpg", "Upload a profile avatar."),
        (user.banner and user.banner != "default_banner.jpg", "Upload a profile banner."),
    ]
    return [message for passed, message in checks if not passed][:4]


# ============================================================
# PUBLIC PROFILE
# ============================================================

@main_bp.route('/bookmarks')
@login_required
def bookmarks():
    """Saved blogs for the current user."""
    page = request.args.get('page', 1, type=int)
    query = Bookmark.query.filter_by(user_id=current_user.id)\
        .join(Blog, Bookmark.blog_id == Blog.id)\
        .filter(Blog.status == 'published')\
        .order_by(Bookmark.created_at.desc())
    pagination = paginate(query, page)
    blogs = [bookmark.blog for bookmark in pagination.items]
    return render_template('profile/bookmarks.html', blogs=blogs, pagination=pagination)


@main_bp.route('/<username>')
def public_profile(username):
    """View a user's public profile."""
    
    # Find the user
    user = User.query.filter_by(username=username).first_or_404()
    
    # Get their published blogs
    blogs = Blog.query.filter_by(user_id=user.id, status='published')\
        .order_by(Blog.created_at.desc()).all()
    
    # Get their published projects
    projects = Project.query.filter_by(user_id=user.id, status='published')\
        .order_by(Project.created_at.desc()).all()
    robotics_projects = RoboticsProject.query.filter_by(user_id=user.id, status='published')\
        .order_by(RoboticsProject.created_at.desc()).all()
    posted_jobs = Job.query.filter_by(posted_by_id=user.id, status='active')\
        .order_by(Job.created_at.desc()).all()
    
    # Check if current user is following this profile
    is_following = False
    if current_user.is_authenticated:
        is_following = current_user.is_following(user)
        if current_user.id != user.id:
            user.profile_views_count = (user.profile_views_count or 0) + 1
            db.session.commit()
    
    # Format skills for display
    skills_list = user.get_skills_list() if user.skills else []
    
    # Social links as dictionary
    social_links = {
        'twitter': user.twitter,
        'linkedin': user.linkedin,
        'github': user.github
    }
    
    # Get followers and following counts
    followers_count = user.followers_count()
    following_count = user.following_count()
    blogs_count = Blog.query.filter_by(user_id=user.id, status='published').count()
    projects_count = Project.query.filter_by(user_id=user.id, status='published').count()
    total_views = db.session.query(db.func.coalesce(db.func.sum(Blog.views_count), 0)).filter_by(
        user_id=user.id,
        status='published'
    ).scalar()
    total_likes = db.session.query(db.func.coalesce(db.func.sum(Blog.likes_count), 0)).filter_by(
        user_id=user.id,
        status='published'
    ).scalar()
    featured_blog = None
    if user.featured_blog_id:
        featured_blog = Blog.query.filter_by(id=user.featured_blog_id, user_id=user.id, status='published').first()
    if not featured_blog:
        featured_blog = Blog.query.filter_by(user_id=user.id, status='published')\
            .order_by(Blog.likes_count.desc(), Blog.views_count.desc(), Blog.created_at.desc()).first()

    featured_project = None
    if user.featured_project_id:
        featured_project = Project.query.filter_by(id=user.featured_project_id, user_id=user.id, status='published').first()
    if not featured_project:
        featured_project = Project.query.filter_by(user_id=user.id, status='published')\
            .order_by(Project.stars_count.desc(), Project.created_at.desc()).first()
    
    # Create a profile-like object with all needed data
    profile_data = {
        'username': user.username,
        'full_name': user.full_name,
        'headline': user.headline,
        'is_verified': user.is_verified,
        'bio': user.bio,
        'location': user.location,
        'website': user.website,
        'resume_url': user.resume_url,
        'avatar_url': url_for('uploaded_file', folder='avatars', filename=user.avatar) if user.avatar else '',
        'banner_url': url_for('uploaded_file', folder='banners', filename=user.banner) if user.banner else '',
        'skills': skills_list,
        'open_to_work': user.open_to_work,
        'availability_status': user.availability_status,
        'job_title': user.job_title,
        'years_experience': user.years_experience,
        'preferred_work_type': user.preferred_work_type,
        'is_recruiter': user.is_recruiter,
        'robotics_specialties': [item.strip() for item in (user.robotics_specialties or '').split(',') if item.strip()],
        'social': social_links,
        'social_links': [
            {'url': value, 'icon': ''} for value in social_links.values() if value
        ],
        'joined_date': user.created_at.strftime('%B %Y'),
        'followers_count': followers_count,
        'following_count': following_count,
        'blogs_count': blogs_count,
        'projects_count': projects_count,
        'total_views': total_views,
        'total_likes': total_likes,
        'profile_views': user.profile_views_count or 0,
        'completion': user.profile_completion(),
        'xp': user.xp_progress,
    }
    
    # Recent activity (simplified - you can expand this)
    activities = []
    
    return render_template('profile/public_profile.html',
                         profile=profile_data,
                         blogs=blogs,
                         projects=projects,
                         robotics_projects=robotics_projects,
                         posted_jobs=posted_jobs,
                         featured_blog=featured_blog,
                         featured_project=featured_project,
                         is_following=is_following,
                         activities=activities)


# ============================================================
# EDIT PROFILE
# ============================================================

@main_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit current user's profile."""
    
    user = current_user
    
    if request.method == 'POST':
        # Update basic info
        user.full_name = request.form.get('full_name', '').strip()
        user.headline = request.form.get('headline', '').strip()
        user.bio = request.form.get('bio', '').strip()
        user.location = request.form.get('location', '').strip()
        user.website = request.form.get('website', '').strip()
        user.resume_url = request.form.get('resume_url', '').strip()
        user.open_to_work = request.form.get('open_to_work') == 'on'
        user.availability_status = request.form.get('availability_status') if request.form.get('availability_status') in {'available-now', 'open-soon', 'not-looking', 'not-specified'} else 'not-specified'
        user.job_title = request.form.get('job_title', '').strip()
        user.years_experience = request.form.get('years_experience', type=int)
        user.preferred_work_type = request.form.get('preferred_work_type') if request.form.get('preferred_work_type') in {'remote', 'onsite', 'hybrid', 'freelance', 'contract'} else None
        user.is_recruiter = request.form.get('is_recruiter') == 'on'
        user.robotics_specialties = request.form.get('robotics_specialties', '').strip()
        featured_blog_id = request.form.get('featured_blog_id', type=int)
        featured_project_id = request.form.get('featured_project_id', type=int)
        user.featured_blog_id = featured_blog_id if Blog.query.filter_by(id=featured_blog_id, user_id=user.id).first() else None
        user.featured_project_id = featured_project_id if Project.query.filter_by(id=featured_project_id, user_id=user.id).first() else None
        
        # Update skills (stored as comma-separated string)
        skills_str = request.form.get('skills', '')
        user.skills = skills_str
        
        # Update social links
        user.twitter = request.form.get('twitter', '').strip()
        user.linkedin = request.form.get('linkedin', '').strip()
        user.github = request.form.get('github', '').strip()
        
        # Handle avatar upload
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                # Delete old avatar if not default
                delete_file(user.avatar, 'avatars')
                # Save new avatar
                filename = save_upload(file, 'avatars', max_size=(400, 400))
                if filename:
                    user.avatar = filename
        
        # Handle banner upload
        if 'banner' in request.files:
            file = request.files['banner']
            if file and file.filename:
                # Delete old banner
                delete_file(user.banner, 'banners')
                # Save new banner
                filename = save_upload(file, 'banners', max_size=(1200, 400))
                if filename:
                    user.banner = filename
        
        db.session.commit()
        maybe_award_profile_completion(user)
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('main.public_profile', username=user.username))
    
    # GET request - show edit form
    user_blogs = Blog.query.filter_by(user_id=user.id, status='published').order_by(Blog.created_at.desc()).all()
    user_projects = Project.query.filter_by(user_id=user.id, status='published').order_by(Project.created_at.desc()).all()
    return render_template('profile/edit_profile.html', profile=user, user_blogs=user_blogs, user_projects=user_projects)


# ============================================================
# DONATION / SUPPORT PAGE
# ============================================================

@main_bp.route('/support')
def support():
    """Donation/support page with UPI QR code."""
    preset_amounts = [49, 99, 199, 499, 999, 2999]
    return render_template('legal/support.html', preset_amounts=preset_amounts)


@main_bp.route('/faq')
def faq():
    """Interactive help center for platform onboarding."""
    return render_template('legal/faq.html')


@main_bp.get('/healthz')
def healthz():
    return jsonify({"ok": True, "status": "healthy"})


@main_bp.route('/api/generate-qr', methods=['POST'])
@rate_limit(max_calls=12, window_seconds=300, scope="donation-qr")
def generate_qr():
    """Generate QR code for specified amount."""
    data = request.get_json(silent=True) or {}
    amount = data.get('amount', 49)

    try:
        amount = Decimal(str(amount)).quantize(Decimal("0.01"))
        if amount < Decimal("1.00") or amount > Decimal("999999.00"):
            return {'error': 'Invalid amount'}, 400
    except (InvalidOperation, ValueError, TypeError):
        return {'error': 'Invalid amount'}, 400

    upi_link = (
        f"upi://pay?"
        f"pa=llaka2937-1@okicici"
        f"&pn=ADITYA"
        f"&am={amount}"
        f"&cu=INR"
    )
    intent = DonationIntent(
        public_id=secrets.token_urlsafe(24),
        user_id=current_user.id if current_user.is_authenticated else None,
        amount=amount,
        upi_url=upi_link,
        ip_address=get_client_ip(),
        user_agent=(request.headers.get("User-Agent") or "")[:500],
    )
    db.session.add(intent)
    db.session.commit()

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(upi_link)
    qr.make(fit=True)
    
    # Convert to base64 for embedding in HTML
    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    qr_code_base64 = base64.b64encode(img_byte_arr.getvalue()).decode()

    return {
        'success': True,
        'qr_code': qr_code_base64,
        'upi_link': upi_link,
        'amount': str(amount),
        'donation_id': intent.public_id,
    }


@main_bp.post('/support/donations/<public_id>/complete')
@rate_limit(max_calls=10, window_seconds=300, scope="donation-complete")
def complete_donation(public_id):
    intent = DonationIntent.query.filter_by(public_id=public_id).first_or_404()
    if intent.status == "qr_generated":
        intent.status = "user_marked_paid"
        intent.completed_at = datetime.utcnow()
        db.session.commit()
    return redirect(url_for('main.support_success', donation_id=intent.public_id))


@main_bp.get('/support/success')
def support_success():
    donation_id = request.args.get("donation_id", "")
    intent = DonationIntent.query.filter_by(public_id=donation_id).first() if donation_id else None
    return render_template('legal/support_success.html', donation=intent)
# SETTINGS
# ============================================================

@main_bp.route('/settings')
@login_required
def settings():
    """User settings page."""
    login_sessions = LoginSession.query.filter_by(user_id=current_user.id).order_by(LoginSession.revoked_at.isnot(None), LoginSession.last_seen_at.desc()).limit(20).all()
    login_events = LoginEvent.query.filter_by(user_id=current_user.id).order_by(LoginEvent.created_at.desc()).limit(30).all()
    donations = DonationIntent.query.filter_by(user_id=current_user.id).order_by(DonationIntent.created_at.desc()).limit(10).all()
    return render_template(
        'profile/settings.html',
        user=current_user,
        login_sessions=login_sessions,
        login_events=login_events,
        donations=donations,
        current_login_session_id=session.get("login_session_id"),
    )


@main_bp.post('/settings/preferences')
@login_required
def update_preferences():
    current_user.email_on_messages = request.form.get('email_on_messages') == 'on'
    current_user.email_on_comments = request.form.get('email_on_comments') == 'on'
    current_user.email_on_follows = request.form.get('email_on_follows') == 'on'
    current_user.email_on_likes = request.form.get('email_on_likes') == 'on'
    current_user.weekly_digest = request.form.get('weekly_digest') == 'on'
    current_user.message_permission = request.form.get('message_permission') if request.form.get('message_permission') in {'everyone', 'followers', 'none'} else 'everyone'
    db.session.commit()
    flash('Preferences updated.', 'success')
    return redirect(url_for('main.settings'))


@main_bp.post('/settings/password')
@login_required
@rate_limit(max_calls=5, window_seconds=300, scope="password")
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    if not current_user.check_password(current_password):
        flash('Current password is incorrect.', 'error')
        return redirect(url_for('main.settings'))
    password_error = validate_password_strength(new_password)
    if password_error:
        flash(password_error, 'error')
        return redirect(url_for('main.settings'))
    current_user.set_password(new_password)
    current_user.clear_failed_logins()
    db.session.commit()
    audit_log(AuditEventType.PASSWORD_CHANGED, description="Password changed from settings")
    flash('Password changed successfully.', 'success')
    return redirect(url_for('main.settings'))


@main_bp.post('/settings/email')
@login_required
@rate_limit(max_calls=3, window_seconds=300, scope="email-change")
def start_email_change():
    new_email = normalize_email(request.form.get('new_email'))
    if not new_email or User.query.filter_by(email=new_email).first():
        flash('Enter a valid unused email address.', 'error')
        return redirect(url_for('main.settings'))
    current_user.pending_email = new_email
    code = issue_otp(current_user, 'email_change')
    from app.utils.emailer import send_otp_email
    send_otp_email(new_email, code)
    db.session.commit()
    flash('Verification code sent to the new email.', 'info')
    return redirect(url_for('main.settings'))


@main_bp.post('/settings/email/verify')
@login_required
def verify_email_change():
    if verify_otp(current_user, 'email_change', request.form.get('otp', '')) and current_user.pending_email:
        current_user.email = current_user.pending_email
        current_user.pending_email = None
        db.session.commit()
        audit_log(AuditEventType.EMAIL_CHANGED, description="Email address changed from settings")
        flash('Email updated.', 'success')
    else:
        flash('Invalid or expired email verification code.', 'error')
    return redirect(url_for('main.settings'))


@main_bp.post('/settings/logout-devices')
@login_required
def logout_all_devices():
    revoke_all_sessions(current_user)
    logout_user()
    flash('All sessions were logged out.', 'info')
    return redirect(url_for('auth.login'))


@main_bp.post('/settings/logout-other-devices')
@login_required
def logout_other_devices():
    count = revoke_other_sessions(current_user)
    flash(f'Logged out {count} other active device{"s" if count != 1 else ""}.', 'success')
    return redirect(url_for('main.settings'))


@main_bp.post('/settings/devices/<public_id>/revoke')
@login_required
def revoke_device(public_id):
    if public_id == session.get("login_session_id"):
        flash('Use logout to end your current session.', 'warning')
        return redirect(url_for('main.settings'))
    if revoke_session(current_user, public_id):
        flash('Device session revoked.', 'success')
    else:
        flash('Device session was not found.', 'error')
    return redirect(url_for('main.settings'))


@main_bp.get('/settings/export')
@login_required
def export_account_data():
    blogs = Blog.query.filter_by(user_id=current_user.id).all()
    projects = Project.query.filter_by(user_id=current_user.id).all()
    bookmarks = Bookmark.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        'user': {
            'username': current_user.username,
            'email': current_user.email,
            'full_name': current_user.full_name,
            'headline': current_user.headline,
            'bio': current_user.bio,
            'location': current_user.location,
            'website': current_user.website,
            'resume_url': current_user.resume_url,
            'skills': current_user.get_skills_list(),
            'created_at': current_user.created_at.isoformat(),
        },
        'blogs': [{'title': blog.title, 'slug': blog.slug, 'status': blog.status, 'created_at': blog.created_at.isoformat()} for blog in blogs],
        'projects': [{'title': project.title, 'slug': project.slug, 'status': project.status, 'created_at': project.created_at.isoformat()} for project in projects],
        'bookmarks': [{'blog_id': bookmark.blog_id, 'created_at': bookmark.created_at.isoformat()} for bookmark in bookmarks],
    })


@main_bp.route('/privacy')
def privacy():
    return render_template('legal/privacy.html')


@main_bp.route('/terms')
def terms():
    return render_template('legal/terms.html')


@main_bp.route('/cookies')
def cookies():
    return render_template('legal/cookies.html')


@main_bp.route('/following')
@login_required
def following_feed():
    following_ids = [follow.followed_id for follow in current_user.followed.limit(500).all()]
    page = request.args.get('page', 1, type=int)
    query = Blog.query.filter(Blog.status == 'published')
    if following_ids:
        query = query.filter(Blog.user_id.in_(following_ids))
    else:
        query = query.filter(False)
    pagination = paginate(query.order_by(Blog.created_at.desc()), page)
    return render_template('feed/following.html', blogs=pagination.items, pagination=pagination)


@main_bp.post('/report/<username>')
@login_required
@rate_limit(max_calls=5, window_seconds=600, scope="report")
def report_user(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user.id == current_user.id:
        flash('You cannot report yourself.', 'error')
        return redirect(url_for('main.public_profile', username=username))
    db.session.add(Report(
        reporter_id=current_user.id,
        reported_user_id=user.id,
        reason=request.form.get('reason', 'other')[:80],
        details=request.form.get('details', '')[:1000],
    ))
    db.session.commit()
    flash('Report submitted for moderation.', 'success')
    return redirect(url_for('main.public_profile', username=username))


@main_bp.post('/block/<username>')
@login_required
@rate_limit(max_calls=10, window_seconds=300, scope="block")
def block_user(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user.id != current_user.id and not Block.query.filter_by(blocker_id=current_user.id, blocked_id=user.id).first():
        db.session.add(Block(blocker_id=current_user.id, blocked_id=user.id))
        db.session.commit()
        flash(f'Blocked @{user.username}.', 'info')
    return redirect(url_for('main.public_profile', username=username))


# ============================================================
# SEARCH
# ============================================================

@main_bp.route('/search')
def search():
    """Search blogs, projects, and users."""
    
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    
    blogs = []
    projects = []
    users = []
    total_results = 0
    
    if query:
        pattern = f'%{query}%'
        # Search blogs by title or content
        blogs = Blog.query.filter(
            Blog.status == 'published',
            db.or_(
                Blog.title.ilike(pattern),
                Blog.content.ilike(pattern),
                Blog.excerpt.ilike(pattern),
                Blog.tags.any(Tag.name.ilike(pattern))
            )
        ).order_by(Blog.likes_count.desc(), Blog.views_count.desc(), Blog.created_at.desc()).limit(10).all()
        
        # Search projects by title or description
        projects = Project.query.filter(
            Project.status == 'published',
            db.or_(
                Project.title.ilike(pattern),
                Project.description.ilike(pattern),
                Project.tags.any(Tag.name.ilike(pattern))
            )
        ).order_by(Project.stars_count.desc(), Project.created_at.desc()).limit(10).all()
        
        # Search users by username or full name
        users = User.query.filter(
            User.active.is_(True),
            db.or_(
                User.username.ilike(pattern),
                User.full_name.ilike(pattern),
                User.headline.ilike(pattern),
                User.skills.ilike(pattern)
            )
        ).limit(10).all()
        
        total_results = len(blogs) + len(projects) + len(users)
    
    return render_template('feed/search_results.html',
                         query=query,
                         blogs=blogs,
                         projects=projects,
                         users=users,
                         total_results=total_results)


@main_bp.get('/tags/suggest')
def suggest_tags():
    query = request.args.get('q', '').strip()
    tag_query = Tag.query
    if query:
        tag_query = tag_query.filter(Tag.name.ilike(f'%{query}%'))
    tags = tag_query.order_by(Tag.name.asc()).limit(12).all()
    return jsonify([{"name": tag.name, "slug": tag.slug} for tag in tags])

# Notifications route moved to social.py
