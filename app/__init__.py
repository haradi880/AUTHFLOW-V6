import logging
import os
import secrets
import time
from pathlib import Path
from logging.handlers import RotatingFileHandler

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from jinja2 import TemplateNotFound
from sqlalchemy import inspect

from config import config_by_name
from app.extensions import db, login_manager, migrate
from app.realtime import init_realtime

# Initialize security extensions
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
)


def create_app(config_name=None):
    app = Flask(__name__)
    config_name = config_name or os.getenv("FLASK_ENV") or os.getenv("APP_ENV") or "default"
    app.config.from_object(config_by_name.get(config_name, config_by_name["default"]))

    init_extensions(app)
    register_blueprints(app)
    register_security(app)
    register_template_helpers(app)
    register_error_handlers(app)
    register_upload_route(app)
    register_well_known_routes(app)
    register_cli(app)
    ensure_upload_folders(app)
    ensure_runtime_schema(app)
    configure_logging(app)
    configure_audit_logging(app)
    init_realtime(app)

    return app


def init_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.blueprint == "api":
            return {"error": "Authentication required"}, 401
        return redirect(url_for("auth.login", next=request.url))


def register_blueprints(app):
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp
    from app.routes.api_v1 import api_v1_bp
    from app.routes.auth import auth_bp
    from app.routes.blog import blog_bp
    from app.routes.devlogs import devlog_bp
    from app.routes.main import main_bp
    from app.routes.project import project_bp
    from app.routes.social import social_bp
    from app.routes.messages import messages_bp
    from app.routes.hiring import hiring_bp
    from app.routes.robotics import robotics_bp
    from app.routes.reputation import reputation_bp
    from app.routes.analyzer import analyzer_bp
    from app.routes.collaboration import collaboration_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(blog_bp)
    app.register_blueprint(devlog_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(hiring_bp)
    app.register_blueprint(robotics_bp)
    app.register_blueprint(reputation_bp)
    app.register_blueprint(analyzer_bp)
    app.register_blueprint(collaboration_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(api_v1_bp, url_prefix="/api/v1")


def register_security(app):
    """Register security middleware and protections."""
    
    @app.before_request
    def sync_login_session():
        """Sync user session data for consistency."""
        if request.endpoint in {"static", "uploaded_file"}:
            return None

        suspended_allowed_endpoints = {
            "auth.account_suspended",
            "auth.account_deleted",
            "auth.logout",
            "main.support",
            "main.submit_support_ticket",
            "main.robots_txt",
            "main.sitemap",
            "main.healthz",
        }
        session_user_id = session.get("_user_id")
        if session_user_id:
            from app.models import User

            try:
                session_user = db.session.get(User, int(session_user_id))
            except (TypeError, ValueError):
                session_user = None
            if session_user and not session_user.active:
                session["suspended_account_email"] = session_user.email
                session["suspended_account_username"] = session_user.username
                if request.endpoint not in suspended_allowed_endpoints:
                    return redirect(url_for("auth.account_suspended"))

        if current_user.is_authenticated:
            if not current_user.active:
                if request.endpoint not in suspended_allowed_endpoints:
                    return redirect(url_for("auth.account_suspended"))

            from app.services.security import touch_current_session

            now = int(time.time())
            touch_interval = 300
            last_touched = int(session.get("login_session_touched_at") or 0)
            should_touch_session = bool(session.get("login_session_id")) and now - last_touched >= touch_interval

            if should_touch_session:
                login_session = touch_current_session(current_user)
                if login_session is None:
                    session.clear()
                    return redirect(url_for("auth.login", next=request.url))
                session["login_session_touched_at"] = now
                db.session.commit()

            # Regenerate session after login to prevent fixation attacks
            if not session.get("_login_session_established"):
                session.permanent = True
                session["_login_session_established"] = True
            
            if session.get("user") != current_user.username:
                session["user"] = current_user.username
            if session.get("is_admin") != current_user.is_admin:
                session["is_admin"] = current_user.is_admin
        return None

    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses."""
        # Security headers
        security_headers = app.config.get("SECURITY_HEADERS", {})
        for header, value in security_headers.items():
            response.headers.setdefault(header, value)
        
        # Add HSTS for production HTTPS
        if not app.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        script_src = "'self' 'unsafe-inline'"
        if app.debug:
            script_src = f"{script_src} 'unsafe-eval'"

        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                f"script-src {script_src}; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "connect-src 'self' ws: wss:; "
                "base-uri 'self'; "
                "frame-ancestors 'self';"
            )
        )
        
        # Cache control based on endpoint
        if request.endpoint == "static":
            response.cache_control.public = True
            response.cache_control.max_age = 604800
            response.headers["Cache-Control"] = "public, max-age=604800"
        elif request.endpoint == "uploaded_file":
            response.cache_control.public = True
            response.cache_control.max_age = 86400
        elif request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        elif request.method == "GET":
            if current_user.is_authenticated or request.endpoint in {
                "auth.login",
                "auth.register",
                "auth.verify_signup",
                "auth.forgot_password",
                "auth.reset_verify",
                "auth.new_password",
            }:
                response.headers["Cache-Control"] = "no-store, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            else:
                response.headers["Cache-Control"] = "public, max-age=120"
        
        return response


def register_template_helpers(app):
    @app.context_processor
    def inject_globals():
        from app.models import Notification, Message, Bookmark
        from flask_login import current_user
        from flask_wtf.csrf import generate_csrf
        
        counts = {'notifications': 0, 'messages': 0, 'bookmarks': 0}
        if current_user.is_authenticated:
            now = int(time.time())
            cached_counts = session.get("unread_counts_cache")
            cache_age = now - int(session.get("unread_counts_cached_at") or 0)
            if isinstance(cached_counts, dict) and cache_age < 15:
                counts.update({key: int(cached_counts.get(key) or 0) for key in counts})
            else:
                counts['notifications'] = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
                counts['messages'] = Message.query.filter_by(recipient_id=current_user.id, is_read=False).count()
                counts['bookmarks'] = Bookmark.query.filter_by(user_id=current_user.id).count()
                session["unread_counts_cache"] = counts
                session["unread_counts_cached_at"] = now
            
        # Flask-WTF provides CSRF token automatically
        return {
            "csrf_token": generate_csrf,
            "unread_counts": counts
        }

    @app.template_filter("upload_url")
    def upload_url(filename, folder):
        return url_for("uploaded_file", folder=folder, filename=filename) if filename else ""


def register_upload_route(app):
    @app.get("/uploads/<folder>/<path:filename>", endpoint="uploaded_file")
    def uploaded_file(folder, filename):
        from app.utils.uploads import supabase_public_url

        allowed_folders = {"avatars", "banners", "blogs", "projects", "devlogs", "messages"}
        if folder not in allowed_folders:
            abort(404)
        if Path(filename).name != filename:
            abort(404)
        upload_root = Path(app.config["UPLOAD_FOLDER"]).resolve()
        folder_path = (upload_root / folder).resolve()
        file_path = (folder_path / filename).resolve()
        if upload_root not in file_path.parents:
            abort(404)
        if file_path.exists():
            return send_from_directory(folder_path, filename)

        public_url = supabase_public_url(folder, filename)
        if public_url:
            return redirect(public_url)

        abort(404)


def register_well_known_routes(app):
    @app.get("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_probe():
        return jsonify({}), 200


def register_cli(app):
    def seed_initial_data():
        from app.models import Category, User

        if not Category.query.first():
            for name, slug in (
                ("AI & Machine Learning", "ai-ml"),
                ("Web Development", "web-dev"),
                ("Mobile Development", "mobile-dev"),
                ("DevOps & Cloud", "devops"),
                ("Data Science", "data-science"),
            ):
                db.session.add(Category(name=name, slug=slug))
        if not User.query.filter_by(email="haradibots.ml@gmail.com").first():
            admin = User(username="admin", email="haradibots.ml@gmail.com", is_admin=True, is_verified=True)
            admin.set_password(os.getenv("ADMIN_PASSWORD", "change-me-admin"))
            db.session.add(admin)
        else:
            admin = User.query.filter_by(email="haradibots.ml@gmail.com").first()
            if admin and (not admin.is_admin or not admin.is_verified):
                admin.is_admin = True
                admin.is_verified = True
        db.session.commit()

    @app.cli.command("init-db")
    def init_db_command():
        db.create_all()
        seed_initial_data()
        print("Database initialized.")

    @app.cli.command("deploy-db")
    def deploy_db_command():
        """Prepare the database safely for container deployments."""
        from flask_migrate import stamp as migrate_stamp, upgrade as migrate_upgrade

        inspector = inspect(db.engine)
        user_tables = set(inspector.get_table_names()) - {"alembic_version"}

        if not user_tables:
            db.create_all()
            seed_initial_data()
            migrate_stamp(revision="head")
            print("Empty database bootstrapped and stamped at migration head.")
            return

        migrate_upgrade()
        seed_initial_data()
        print("Database migrations applied.")


def register_error_handlers(app):
    @app.errorhandler(429)
    def too_many_requests(error):
        return render_template("errors/400.html", error=error) if _template_exists(app, "errors/400.html") else (str(error), 429)

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html", error=error) if _template_exists(app, "errors/400.html") else (str(error), 400)

    @app.errorhandler(403)
    def forbidden(error):
        if _template_exists(app, "errors/403.html"):
            return render_template("errors/403.html"), 403
        return "Access denied", 403

    @app.errorhandler(404)
    def not_found(error):
        if _template_exists(app, "errors/404.html"):
            return render_template("errors/404.html"), 404
        return "Page not found", 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled server error")
        if _template_exists(app, "errors/500.html"):
            return render_template("errors/500.html"), 500
        return "Internal server error", 500


def _template_exists(app, template_name):
    try:
        app.jinja_env.loader.get_source(app.jinja_env, template_name)
        return True
    except TemplateNotFound:
        return False


def ensure_upload_folders(app):
    for folder in ("avatars", "banners", "blogs", "projects", "devlogs", "messages"):
        Path(app.config["UPLOAD_FOLDER"], folder).mkdir(parents=True, exist_ok=True)


def ensure_runtime_schema(app):
    """Additive SQLite-only compatibility for local dev databases."""
    if not app.config.get("SQLALCHEMY_DATABASE_URI", "").startswith("sqlite"):
        return

    additions = {
        "headline": "VARCHAR(160)",
        "resume_url": "VARCHAR(500)",
        "featured_blog_id": "INTEGER",
        "featured_project_id": "INTEGER",
        "pending_email": "VARCHAR(255)",
        "email_on_messages": "BOOLEAN NOT NULL DEFAULT 1",
        "email_on_comments": "BOOLEAN NOT NULL DEFAULT 1",
        "email_on_follows": "BOOLEAN NOT NULL DEFAULT 1",
        "email_on_likes": "BOOLEAN NOT NULL DEFAULT 0",
        "weekly_digest": "BOOLEAN NOT NULL DEFAULT 1",
        "message_permission": "VARCHAR(20) NOT NULL DEFAULT 'everyone'",
        "profile_views_count": "INTEGER NOT NULL DEFAULT 0",
        "xp_total": "INTEGER NOT NULL DEFAULT 0",
        "level": "INTEGER NOT NULL DEFAULT 1",
        "profile_xp_awarded_at": "DATETIME",
        # Reputation
        "reputation_points": "INTEGER NOT NULL DEFAULT 0",
        "trust_level": "INTEGER NOT NULL DEFAULT 1",
        "contributor_tier": "VARCHAR(30) NOT NULL DEFAULT 'newcomer'",
        "is_verified_creator": "BOOLEAN NOT NULL DEFAULT 0",
        # Hiring
        "open_to_work": "BOOLEAN NOT NULL DEFAULT 0",
        "availability_status": "VARCHAR(30) NOT NULL DEFAULT 'not-specified'",
        "job_title": "VARCHAR(160)",
        "years_experience": "INTEGER",
        "preferred_work_type": "VARCHAR(30)",
        "is_recruiter": "BOOLEAN NOT NULL DEFAULT 0",
        # Robotics
        "robotics_specialties": "TEXT",
        # Analysis
        "portfolio_score": "INTEGER",
        "last_analyzed_at": "DATETIME",
    }

    with app.app_context():
        inspector = inspect(db.engine)
        if not inspector.has_table("users"):
            return
        existing = {column["name"] for column in inspector.get_columns("users")}
        with db.engine.begin() as connection:
            for name, column_type in additions.items():
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {name} {column_type}")

        table_additions = {
            "notifications": {
                "seen_at": "DATETIME",
                "read_at": "DATETIME",
                "delivered_at": "DATETIME",
                "email_sent_at": "DATETIME",
                "email_status": "VARCHAR(30) NOT NULL DEFAULT 'pending'",
                "retry_count": "INTEGER NOT NULL DEFAULT 0",
                "last_error": "VARCHAR(500)",
                "priority": "VARCHAR(20) NOT NULL DEFAULT 'normal'",
                "entity_type": "VARCHAR(60)",
                "entity_id": "INTEGER",
            },
            "job_applications": {
                "recruiter_response": "VARCHAR(1000)",
                "status_changed_at": "DATETIME",
                "reviewed_by_id": "INTEGER",
            },
            "messages": {
                "attachment_filename": "VARCHAR(255)",
                "attachment_original_name": "VARCHAR(255)",
                "attachment_mime": "VARCHAR(120)",
                "attachment_size": "INTEGER",
            },
        }
        with db.engine.begin() as connection:
            for table_name, columns in table_additions.items():
                if not inspector.has_table(table_name):
                    continue
                existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
                for name, column_type in columns.items():
                    if name not in existing_columns:
                        connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {name} {column_type}")

        if not inspector.has_table("support_tickets"):
            db.create_all()


def configure_logging(app):
    logging.basicConfig(level=logging.INFO if not app.debug else logging.DEBUG)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    handler = RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000, backupCount=3)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    if not any(isinstance(h, RotatingFileHandler) for h in app.logger.handlers):
        app.logger.addHandler(handler)


def configure_audit_logging(app):
    """Configure security audit logging."""
    from app.utils.audit import configure_audit_logging as setup_audit
    setup_audit(app)
