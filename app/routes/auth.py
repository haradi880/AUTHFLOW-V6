from urllib.parse import urlparse, urljoin

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for, current_app
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import User
from app.services.auth import (
    authenticate_user,
    issue_otp,
    normalize_email,
    register_user,
    reset_password,
    start_password_reset,
    validate_password_strength,
    verify_otp,
)
from app.services.gamification import award_xp
from app.utils.rate_limit import rate_limit

auth_bp = Blueprint("auth", __name__)


def is_safe_redirect_url(target):
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in {"http", "https"} and ref_url.netloc == test_url.netloc


@auth_bp.route("/register", methods=["GET", "POST"])
@rate_limit(max_calls=8, window_seconds=300, scope="register")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")

        if len(username) < 3:
            flash("Username must be at least 3 characters.", "error")
            return render_template("auth/register.html")
        password_error = validate_password_strength(password)
        if password_error:
            flash(password_error, "error")
            return render_template("auth/register.html")
        if User.query.filter_by(username=username).first():
            flash("Username already taken. Please choose another.", "error")
            return render_template("auth/register.html")
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please log in instead.", "error")
            return render_template("auth/register.html")

        register_user(username, email, password)
        session["verify_email"] = email
        flash("Account created. Please verify your email with the code we sent.", "success")
        return redirect(url_for("auth.verify_signup"))

    return render_template("auth/register.html")


@auth_bp.route("/verify-signup", methods=["GET", "POST"])
def verify_signup():
    email = session.get("verify_email")
    if not email:
        flash("Please register first.", "warning")
        return redirect(url_for("auth.register"))

    user = User.query.filter_by(email=email).first_or_404()
    if request.method == "POST":
        if verify_otp(user, "email_verification", request.form.get("otp", "")):
            session.pop("verify_email", None)
            flash("Email verified successfully. You can now log in.", "success")
            return redirect(url_for("auth.login"))
        flash("Invalid or expired OTP. Please try again.", "error")

    return render_template("auth/verify.html")


@auth_bp.post("/resend-verification")
@rate_limit(max_calls=3, window_seconds=300, scope="otp")
def resend_verification():
    email = session.get("verify_email")
    user = User.query.filter_by(email=email).first() if email else None
    if user and not user.is_verified:
        code = issue_otp(user, "email_verification")
        from app.utils.emailer import send_otp_email

        send_otp_email(user.email, code)
    flash("If a verification is pending, a new code has been sent.", "info")
    return redirect(url_for("auth.verify_signup"))


@auth_bp.post("/resend-otp")
@rate_limit(max_calls=3, window_seconds=300, scope="otp-json")
def resend_otp():
    purpose = request.form.get("purpose") or (request.get_json(silent=True) or {}).get("purpose")
    if purpose == "password_reset":
        email = session.get("reset_email")
        user = User.query.filter_by(email=email).first() if email else None
    else:
        purpose = "email_verification"
        email = session.get("verify_email")
        user = User.query.filter_by(email=email).first() if email else None

    if user and (purpose == "password_reset" or not user.is_verified):
        code = issue_otp(user, purpose)
        from app.utils.emailer import send_otp_email

        send_otp_email(user.email, code)
    if request.accept_mimetypes.best == "application/json" or request.is_json:
        return jsonify({"success": True, "message": "If a code is pending, a new one has been sent."})
    flash("If a code is pending, a new one has been sent.", "info")
    return redirect(url_for("auth.reset_verify" if purpose == "password_reset" else "auth.verify_signup"))


@auth_bp.route("/login", methods=["GET", "POST"])
@rate_limit(max_calls=8, window_seconds=300, scope="login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        user, error = authenticate_user(request.form.get("email"), request.form.get("password", ""))
        if error:
            if user and not user.is_verified:
                session["verify_email"] = user.email
                flash(error, "warning")
                return redirect(url_for("auth.verify_signup"))
            flash(error, "error")
            return render_template("auth/login.html")

        remember = request.form.get("remember") == "on"
        login_user(user, remember=remember)
        session.permanent = remember
        session["user"] = user.username
        session["is_admin"] = user.is_admin
        award_xp(user, "daily_login")
        flash(f"Welcome back, {user.username}!", "success")
        next_page = request.args.get("next")
        return redirect(next_page if is_safe_redirect_url(next_page) else url_for("main.home"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("user", None)
    session.pop("is_admin", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot", methods=["GET", "POST"])
@rate_limit(max_calls=5, window_seconds=300, scope="forgot")
def forgot_password():
    if request.method == "POST":
        email = normalize_email(request.form.get("email"))
        start_password_reset(email)
        session["reset_email"] = email
        flash("If that email exists, we have sent a reset code.", "info")
        return redirect(url_for("auth.reset_verify"))
    return render_template("auth/forgot.html")


@auth_bp.route("/reset-verify", methods=["GET", "POST"])
def reset_verify():
    email = session.get("reset_email")
    if not email:
        flash("Please request a password reset first.", "warning")
        return redirect(url_for("auth.forgot_password"))
    user = User.query.filter_by(email=email).first()

    if request.method == "POST":
        if user and verify_otp(user, "password_reset", request.form.get("otp", "")):
            session["otp_verified"] = True
            return redirect(url_for("auth.new_password"))
        flash("Invalid or expired OTP.", "error")

    return render_template("auth/reset_verify.html")


@auth_bp.route("/new-password", methods=["GET", "POST"])
def new_password():
    if not session.get("otp_verified"):
        flash("Please verify your identity first.", "warning")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        password_error = validate_password_strength(password)
        if password_error:
            flash(password_error, "error")
            return render_template("auth/new_password.html")
        user = User.query.filter_by(email=session.get("reset_email")).first_or_404()
        reset_password(user, password)
        session.pop("reset_email", None)
        session.pop("otp_verified", None)
        flash("Password reset successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/new_password.html")


@auth_bp.route("/confirm-password", methods=["GET", "POST"])
@login_required
def confirm_password():
    """Confirm password for sensitive operations like deletion."""
    from app.utils.password_confirm import set_password_confirmed, confirm_password as verify_pwd
    
    if request.method == "POST":
        password = request.form.get("password", "").strip()
        
        if not password:
            flash("Please enter your password.", "error")
            return render_template("auth/confirm_password.html")
        
        if verify_pwd(password):
            set_password_confirmed()
            flash("Password confirmed. You can now proceed.", "success")
            next_url = session.pop("confirm_password_next", url_for("main.home"))
            return redirect(next_url)
        else:
            flash("Incorrect password. Please try again.", "error")
    
    return render_template("auth/confirm_password.html")


@auth_bp.route("/delete-account", methods=["GET", "POST"])
@login_required
@rate_limit(max_calls=3, window_seconds=3600, scope="account_delete")
def delete_account():
    """Delete user account with data cleanup."""
    from app.utils.audit import audit_log, AuditEventType
    from app.utils.soft_delete import soft_delete
    from app.utils.uploads_secure import delete_file_secure
    
    if request.method == "POST":
        # Verify password
        password = request.form.get("password", "").strip()
        if not password or not current_user.check_password(password):
            flash("Invalid password. Account deletion cancelled.", "error")
            return render_template("auth/delete_account.html")
        
        # Verify confirmation checkbox
        confirmed = request.form.get("confirm_delete") == "on"
        if not confirmed:
            flash("Please check the confirmation box.", "error")
            return render_template("auth/delete_account.html")
        
        # Start account deletion process
        user_id = current_user.id
        username = current_user.username
        email = current_user.email
        
        try:
            # 1. Delete uploaded files
            if current_user.avatar and current_user.avatar != "default.jpg":
                delete_file_secure(current_user.avatar, "avatars")
            if current_user.banner and current_user.banner != "default_banner.jpg":
                delete_file_secure(current_user.banner, "banners")
            
            # 2. Delete user's content (soft delete for recovery)
            from app.models import Blog, Project, DevLog
            
            for blog in Blog.query.filter_by(user_id=user_id).all():
                delete_file_secure(blog.thumbnail, "blogs")
                soft_delete(blog, "blog", user_id=user_id, reason="Account deletion")
            
            for project in Project.query.filter_by(user_id=user_id).all():
                delete_file_secure(project.thumbnail, "projects")
                for image in project.images.all():
                    delete_file_secure(image.filename, "projects")
                soft_delete(project, "project", user_id=user_id, reason="Account deletion")
            
            for devlog in DevLog.query.filter_by(user_id=user_id).all():
                for media in devlog.media.all():
                    delete_file_secure(media.filename, "devlogs")
                soft_delete(devlog, "devlog", user_id=user_id, reason="Account deletion")
            
            # 3. Log the deletion
            audit_log(
                event_type=AuditEventType.ACCOUNT_DELETED,
                description=f"Account deleted by user: {username}",
                target_id=user_id,
                target_type="user",
                actor_id=user_id,
                actor_username=username,
                metadata={"email": email}
            )
            
            # 4. Delete the user account
            db.session.delete(current_user)
            db.session.commit()
            
            # 5. Clear session
            logout_user()
            session.clear()
            
            flash(f"Account {username} has been permanently deleted along with all associated content.", "success")
            return redirect(url_for("auth.login"))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Account deletion failed for {username}: {e}")
            flash("Error deleting account. Please contact support.", "error")
            return render_template("auth/delete_account.html")
    
    return render_template("auth/delete_account.html")
