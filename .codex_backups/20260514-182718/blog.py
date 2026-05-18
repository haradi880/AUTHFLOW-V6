"""
Blog Routes - Create, Read, Update, Delete blog posts.
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Blog, Category, Tag, Comment, BlogLike, Bookmark
from app.services.content import calculate_reading_time, generate_slug, render_markdown, sync_tags
from app.services.gamification import award_xp
from app.utils.helpers import paginate, create_notification
from app.utils.uploads import delete_file, save_upload
from app.utils.decorators import owner_required
from app.utils.rate_limit import rate_limit

# Create the blueprint
blog_bp = Blueprint('blog', __name__)


# ============================================================
# BLOG LISTING (Feed)
# ============================================================

@blog_bp.route('/blogs')
def blogs_feed():
    """Display all published blogs."""
    
    # Get filter parameters
    category = request.args.get('category')
    tag = request.args.get('tag')
    search = request.args.get('q', '').strip()
    sort = request.args.get('sort', 'latest')
    page = request.args.get('page', 1, type=int)
    
    # Start with base query - only published blogs
    query = Blog.query.filter_by(status='published')
    
    # Apply category filter
    if category:
        cat = Category.query.filter_by(slug=category).first()
        if cat:
            query = query.filter_by(category_id=cat.id)
    
    # Apply tag filter
    if tag:
        query = query.filter(Blog.tags.any(Tag.slug == tag))

    if search:
        query = query.filter(
            db.or_(
                Blog.title.ilike(f'%{search}%'),
                Blog.content.ilike(f'%{search}%'),
                Blog.excerpt.ilike(f'%{search}%')
            )
        )
    
    # Apply sorting
    if sort == 'trending':
        query = query.order_by(Blog.views_count.desc())
    elif sort == 'most_read':
        query = query.order_by(Blog.views_count.desc())
    elif sort == 'most_liked':
        query = query.order_by(Blog.likes_count.desc())
    else:  # latest
        query = query.order_by(Blog.created_at.desc())
    
    # Paginate results
    pagination = paginate(query, page)
    blogs = pagination.items
    
    # Get all categories for filter dropdown
    categories = Category.query.all()
    
    # Get trending tags
    trending_tags = Tag.query.limit(10).all()
    
    # Get featured blog (most liked recent blog)
    featured = Blog.query.filter_by(status='published')\
        .order_by(Blog.likes_count.desc()).first()
    
    return render_template('feed/blogs_feed.html',
                         blogs=blogs,
                         pagination=pagination,
                         categories=categories,
                         trending_tags=trending_tags,
                         featured_blog=featured)


# ============================================================
# BLOG DETAIL PAGE
# ============================================================

@blog_bp.route('/blog/<slug>')
def blog_detail(slug):
    """View a single blog post."""
    
    # Find the blog
    blog = Blog.query.filter_by(slug=slug, status='published').first_or_404()
    
    # Increment view count
    blog.views_count += 1
    db.session.commit()
    recent_ids = [item for item in session.get('recently_viewed_blogs', []) if item != blog.id]
    session['recently_viewed_blogs'] = [blog.id] + recent_ids[:5]
    
    # Get comments
    comments = Comment.query.filter_by(blog_id=blog.id, parent_id=None)\
        .order_by(Comment.created_at.desc()).all()
    
    # Get related posts (same category)
    related = Blog.query.filter(
        Blog.id != blog.id,
        Blog.status == 'published',
        Blog.category_id == blog.category_id
    ).limit(3).all()
    
    # Check if current user liked/bookmarked this
    is_liked = blog.is_liked_by(current_user) if current_user.is_authenticated else False
    is_bookmarked = blog.is_bookmarked_by(current_user) if current_user.is_authenticated else False
    is_following_author = current_user.is_following(blog.author) if current_user.is_authenticated else False
    
    blog.content = render_markdown(blog.content)
    return render_template('content/blog_detail.html',
                         blog=blog,
                         comments=comments,
                         related_posts=related,
                         is_liked=is_liked,
                         is_bookmarked=is_bookmarked,
                         is_following_author=is_following_author)


# ============================================================
# CREATE BLOG
# ============================================================

@blog_bp.route('/upload/blog', methods=['GET', 'POST'])
@login_required
def create_blog():
    """Create a new blog post."""
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '')  # Markdown content
        excerpt = request.form.get('excerpt', '').strip()
        category_id = request.form.get('category_id', type=int)
        tags_str = request.form.get('tags', '')  # Comma-separated tags
        status = request.form.get('status', 'draft')  # draft or published
        
        # Generate unique slug from title
        slug = generate_slug(title, Blog)
        
        # Calculate reading time
        reading_time = calculate_reading_time(content)
        
        # Create blog object
        blog = Blog(
            title=title,
            slug=slug,
            content=content,
            excerpt=excerpt[:500] if excerpt else content[:200],
            reading_time=reading_time,
            status=status,
            user_id=current_user.id,
            category_id=category_id
        )
        
        # Set publish date if published
        if status == 'published':
            blog.published_at = datetime.utcnow()
        
        # Handle thumbnail upload
        if 'thumbnail' in request.files:
            file = request.files['thumbnail']
            if file.filename:
                filename = save_upload(file, 'blogs')
                if filename:
                    blog.thumbnail = filename
                else:
                    flash('Thumbnail upload failed', 'error')
        
        sync_tags(blog, tags_str)
        
        db.session.add(blog)
        db.session.commit()
        if blog.status == 'published':
            award_xp(current_user, "publish_blog", source=blog)
        
        flash('Blog post created successfully!', 'success')
        return redirect(url_for('blog.blog_detail', slug=blog.slug))
    
    # GET request - show form
    categories = Category.query.all()
    return render_template('content/upload_blog.html', categories=categories)


# ============================================================
# EDIT BLOG
# ============================================================

@blog_bp.route('/blog/<int:blog_id>/edit', methods=['GET', 'POST'])
@login_required
@owner_required(Blog)
def edit_blog(blog_id):
    """Edit an existing blog post."""
    
    blog = Blog.query.get_or_404(blog_id)
    
    if request.method == 'POST':
        blog.title = request.form.get('title', '').strip()
        blog.content = request.form.get('content', '')
        blog.excerpt = request.form.get('excerpt', '').strip()[:500]
        blog.category_id = request.form.get('category_id', type=int)
        blog.status = request.form.get('status', 'draft')
        
        # Update reading time
        blog.calculate_reading_time()
        
        # Set publish date if publishing for first time
        was_published = bool(blog.published_at)
        if blog.status == 'published' and not blog.published_at:
            blog.published_at = datetime.utcnow()
        
        # Handle thumbnail update
        if 'thumbnail' in request.files:
            file = request.files['thumbnail']
            if file.filename:
                # Delete old thumbnail
                delete_file_secure(blog.thumbnail, 'blogs')
                # Save new thumbnail
                filename, error = save_upload_secure(file, 'blogs')
                if filename:
                    blog.thumbnail = filename
                else:
                    flash(f'Thumbnail upload failed: {error}', 'error')
        
        sync_tags(blog, request.form.get('tags', ''))
        
        db.session.commit()
        if blog.status == 'published' and not was_published:
            award_xp(current_user, "publish_blog", source=blog)
        flash('Blog updated successfully!', 'success')
        return redirect(url_for('blog.blog_detail', slug=blog.slug))
    
    categories = Category.query.all()
    return render_template('content/upload_blog.html', 
                         blog=blog, 
                         categories=categories,
                         editing=True)


# ============================================================
# DELETE BLOG
# ============================================================

@blog_bp.route('/blog/<int:blog_id>/delete', methods=['POST'])
@login_required
@owner_required(Blog)
def delete_blog(blog_id):
    """Delete a blog post securely with audit trail."""
    from app.utils.password_confirm import password_required, confirm_password
    from app.utils.soft_delete import soft_delete
    from app.utils.audit import audit_log, AuditEventType
    
    blog = Blog.query.get_or_404(blog_id)
    
    # Verify password for this sensitive operation
    password = request.form.get('password', '').strip()
    if not password or not confirm_password(password):
        flash('Invalid password. Deletion cancelled.', 'error')
        return redirect(url_for('blog.blog_detail', slug=blog.slug))
    
    # Delete thumbnail file
    from app.utils.uploads_secure import delete_file_secure
    delete_file_secure(blog.thumbnail, 'blogs')
    
    # Soft delete the blog (keeps archived copy for recovery)
    if soft_delete(
        blog,
        content_type='blog',
        user_id=current_user.id,
        reason='User deletion',
        recovery_days=30
    ):
        flash('Blog deleted successfully. You can recover it within 30 days.', 'success')
        audit_log(
            event_type=AuditEventType.CONTENT_DELETED,
            description=f"Deleted blog: {blog.title}",
            target_id=blog_id,
            target_type='blog',
            metadata={"slug": blog.slug}
        )
    else:
        flash('Error deleting blog. Please try again.', 'error')
    
    return redirect(url_for('main.home'))


# ============================================================
# ADD COMMENT
# ============================================================

@blog_bp.route('/blog/<int:blog_id>/comment', methods=['POST'])
@login_required
@rate_limit(max_calls=10, window_seconds=300, scope="comments")
def add_comment(blog_id):
    """Add a comment to a blog post."""
    
    blog = Blog.query.get_or_404(blog_id)
    content = request.form.get('content', '').strip()
    
    if not content:
        flash('Comment cannot be empty.', 'error')
        return redirect(url_for('blog.blog_detail', slug=blog.slug))
    
    # Create comment
    comment = Comment(
        content=content,
        user_id=current_user.id,
        blog_id=blog_id
    )
    
    # Update comment count
    blog.comments_count += 1
    
    db.session.add(comment)
    db.session.commit()
    award_xp(current_user, "comment", source=comment)
    
    # Notify blog author
    if blog.user_id != current_user.id:
        create_notification(
            user=blog.author,
            action='comment',
            message=f'{current_user.username} commented on your blog "{blog.title}"',
            link=url_for('blog.blog_detail', slug=blog.slug),
            from_user=current_user
        )
    
    flash('Comment added!', 'success')
    return redirect(url_for('blog.blog_detail', slug=blog.slug))


# ============================================================
# LIKE BLOG
# ============================================================

@blog_bp.route('/blog/<int:blog_id>/like', methods=['POST'])
@login_required
def like_blog(blog_id):
    """Like or unlike a blog post."""
    
    blog = Blog.query.get_or_404(blog_id)
    
    # Check if already liked
    existing_like = BlogLike.query.filter_by(
        user_id=current_user.id, 
        blog_id=blog_id
    ).first()
    
    if existing_like:
        # Unlike
        db.session.delete(existing_like)
        blog.likes_count = max(0, blog.likes_count - 1)
        db.session.commit()
        return {'status': 'unliked', 'count': blog.likes_count}
    else:
        # Like
        like = BlogLike(user_id=current_user.id, blog_id=blog_id)
        db.session.add(like)
        blog.likes_count += 1
        db.session.commit()
        if blog.user_id != current_user.id:
            award_xp(blog.author, "receive_blog_like", source=like)
        
        # Notify author
        if blog.user_id != current_user.id:
            create_notification(
                user=blog.author,
                action='like',
                message=f'{current_user.username} liked your blog "{blog.title}"',
                link=url_for('blog.blog_detail', slug=blog.slug),
                from_user=current_user
            )
        
        return {'status': 'liked', 'count': blog.likes_count}


# ============================================================
# BOOKMARK BLOG
# ============================================================

@blog_bp.route('/blog/<int:blog_id>/bookmark', methods=['POST'])
@login_required
def bookmark_blog(blog_id):
    """Bookmark or unbookmark a blog post."""
    
    blog = Blog.query.get_or_404(blog_id)
    
    existing = Bookmark.query.filter_by(
        user_id=current_user.id,
        blog_id=blog_id
    ).first()
    
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return {'status': 'unbookmarked'}
    else:
        bookmark = Bookmark(user_id=current_user.id, blog_id=blog_id)
        db.session.add(bookmark)
        db.session.commit()
        return {'status': 'bookmarked'}
