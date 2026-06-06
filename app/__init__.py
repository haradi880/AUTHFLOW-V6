import logging
import json
import os
import secrets
import sys
import time
from pathlib import Path
from logging.handlers import RotatingFileHandler

import click
from flask import Flask, abort, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask.sessions import SecureCookieSessionInterface
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect
from jinja2 import TemplateNotFound
from markupsafe import Markup, escape
from sqlalchemy import inspect

from config import config_by_name
from app.extensions import db, limiter, login_manager, migrate
from app.realtime import init_realtime

# Initialize security extensions
csrf = CSRFProtect()


class HaradiBotsSessionInterface(SecureCookieSessionInterface):
    """Avoid Set-Cookie churn for anonymous public pages with no incoming session."""

    def save_session(self, app, session_obj, response):
        if not session_obj and session_obj.modified:
            cookie_name = self.get_cookie_name(app)
            if not request.cookies.get(cookie_name):
                return
        return super().save_session(app, session_obj, response)


def create_app(config_name=None):
    app = Flask(__name__)
    config_name = config_name or os.getenv("FLASK_ENV") or os.getenv("APP_ENV") or "default"
    app.config.from_object(config_by_name.get(config_name, config_by_name["default"]))
    app.session_interface = HaradiBotsSessionInterface()

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
    running_production_check = "production-check" in sys.argv
    if (
        not running_production_check
        and not app.config.get("TESTING")
        and not app.debug
        and app.config.get("RATELIMIT_STORAGE_URI") == "memory://"
    ):
        raise RuntimeError("Production rate limiting requires RATELIMIT_STORAGE_URI backed by Redis.")
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
    def attach_observability_context():
        from app.services.observability import start_request_timer

        start_request_timer()
    
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
            "main.sitemap_index",
            "main.social_card",
            "main.healthz",
            "main.readyz",
            "main.metrics",
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
        from app.services.observability import record_request, structured_log

        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id

        duration = record_request(response)
        if app.config.get("REQUEST_LOGGING_ENABLED") and request.endpoint not in {"static"}:
            structured_log(
                app.logger,
                logging.INFO if response.status_code < 500 else logging.ERROR,
                "http_request",
                status=response.status_code,
                endpoint=request.endpoint,
                duration_ms=round(duration * 1000, 2),
                user_id=current_user.get_id() if current_user.is_authenticated else None,
            )

        # Security headers
        security_headers = app.config.get("SECURITY_HEADERS", {})
        for header, value in security_headers.items():
            response.headers.setdefault(header, value)
        
        # Add HSTS for production HTTPS
        if not app.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        script_src = "'self' 'unsafe-inline' https://cdn.jsdelivr.net"
        upgrade_insecure = "upgrade-insecure-requests; " if not app.debug else ""

        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                f"script-src {script_src}; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "media-src 'self' https://assets.mixkit.co; "
                "connect-src 'self' ws: wss:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "frame-src 'self'; "
                "manifest-src 'self'; "
                f"{upgrade_insecure}"
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
                response.headers.setdefault("Cache-Control", "public, max-age=120")
        
        return response


def register_template_helpers(app):
    @app.context_processor
    def inject_globals():
        from app.models import Notification, Message, Bookmark, ConversationMember
        from flask_login import current_user
        from flask_wtf.csrf import generate_csrf

        def user_avatar(user, classes="avatar-v2 avatar-v2--sm", style="", href=None, title=None):
            username = getattr(user, "username", "") or "User"
            avatar_name = getattr(user, "avatar", None)
            avatar_url = ""
            if avatar_name and avatar_name != "default.jpg":
                try:
                    avatar_url = getattr(user, "avatar_url", "") or ""
                except RuntimeError:
                    avatar_url = ""

            if avatar_url:
                # URL and alt text are escaped before markup wrapping.
                inner = Markup(  # nosec B704
                    '<img src="{}" alt="{}" loading="lazy">'.format(
                        escape(avatar_url),
                        escape(username),
                    )
                )
            else:
                inner = escape(username[:1].upper() if username else "?")

            tag = "a" if href else "div"
            attrs = [f'class="{escape(classes)}"']
            if style:
                attrs.append(f'style="{escape(style)}"')
            if href:
                attrs.append(f'href="{escape(href)}"')
            if title:
                attrs.append(f'title="{escape(title)}"')
                attrs.append(f'aria-label="{escape(title)}"')

            return Markup(f"<{tag} {' '.join(attrs)}>{inner}</{tag}>")  # nosec B704
        
        counts = {'notifications': 0, 'messages': 0, 'bookmarks': 0}
        if current_user.is_authenticated:
            now = int(time.time())
            cached_counts = session.get("unread_counts_cache")
            cache_age = now - int(session.get("unread_counts_cached_at") or 0)
            if isinstance(cached_counts, dict) and cache_age < 15:
                counts.update({key: int(cached_counts.get(key) or 0) for key in counts})
            else:
                notification_count = db.session.query(db.func.count(Notification.id)).filter(
                    Notification.user_id == current_user.id,
                    Notification.is_read.is_(False),
                ).scalar_subquery()
                conversation_message_count = db.session.query(db.func.count(Message.id)).join(
                    ConversationMember,
                    Message.conversation_id == ConversationMember.conversation_id,
                ).filter(
                    ConversationMember.user_id == current_user.id,
                    ConversationMember.is_active.is_(True),
                    Message.sender_id != current_user.id,
                    db.or_(
                        ConversationMember.last_read_message_id.is_(None),
                        Message.id > ConversationMember.last_read_message_id,
                    ),
                ).scalar_subquery()
                legacy_message_count = db.session.query(db.func.count(Message.id)).filter(
                    Message.conversation_id.is_(None),
                    Message.recipient_id == current_user.id,
                    Message.is_read.is_(False),
                ).scalar_subquery()
                bookmark_count = db.session.query(db.func.count(Bookmark.id)).filter(
                    Bookmark.user_id == current_user.id,
                ).scalar_subquery()
                notif_count, msg_count, saved_count = db.session.query(
                    notification_count,
                    conversation_message_count + legacy_message_count,
                    bookmark_count,
                ).one()
                counts['notifications'] = notif_count
                counts['messages'] = msg_count
                counts['bookmarks'] = saved_count
                session["unread_counts_cache"] = counts
                session["unread_counts_cached_at"] = now
            
        def public_url_for(endpoint, **values):
            values.pop("_external", None)
            values.pop("_scheme", None)
            path = url_for(endpoint, **values)
            base = (app.config.get("PUBLIC_BASE_URL") or request.host_url).rstrip("/")
            return f"{base}{path}" if path.startswith("/") else path

        def current_public_url():
            endpoint = request.endpoint
            if not endpoint or endpoint == "static":
                return request.base_url
            try:
                return public_url_for(endpoint, **(request.view_args or {}))
            except Exception:
                return request.base_url

        csrf_public_endpoints = {
            "auth.login",
            "auth.register",
            "auth.verify_signup",
            "auth.forgot_password",
            "auth.reset_verify",
            "auth.new_password",
            "auth.account_suspended",
            "auth.account_deleted",
            "main.support",
            "main.submit_support_ticket",
            "main.support_donate",
        }
        csrf_required = current_user.is_authenticated or request.endpoint in csrf_public_endpoints

        return {
            "csrf_token": generate_csrf,
            "unread_counts": counts,
            "user_avatar": user_avatar,
            "csrf_required": csrf_required,
            "public_url_for": public_url_for,
            "current_public_url": current_public_url,
            "default_og_image_url": public_url_for("main.social_card"),
        }

    @app.template_filter("upload_url")
    def upload_url(filename, folder):
        from app.utils.uploads import public_upload_url

        return public_upload_url(folder, filename)


def register_upload_route(app):
    @app.get("/uploads/<folder>/<path:filename>", endpoint="uploaded_file")
    def uploaded_file(folder, filename):
        from app.utils.uploads import supabase_public_url

        allowed_folders = {"avatars", "banners", "blogs", "projects", "devlogs"}
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
    def prepare_internal_test_schema():
        if app.config.get("TESTING"):
            with app.app_context():
                db.create_all()

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
        from flask_migrate import upgrade as migrate_upgrade

        migrate_upgrade()
        seed_initial_data()
        print("Database migrated and initialized.")

    @app.cli.command("deploy-db")
    def deploy_db_command():
        """Prepare the database safely for container deployments."""
        from flask_migrate import upgrade as migrate_upgrade

        migrate_upgrade()
        seed_initial_data()
        print("Database migrations applied.")

    @app.cli.command("production-check")
    @click.option("--json", "as_json", is_flag=True, help="Print machine-readable JSON.")
    @click.option("--warnings-as-errors", is_flag=True, help="Return a failure when warnings are present.")
    def production_check_command(as_json=False, warnings_as_errors=False):
        """Validate deployment-critical production configuration."""
        from app.services.production_checks import production_check_summary, run_production_checks

        checks = run_production_checks(app.config)
        summary = production_check_summary(checks)
        payload = {
            "summary": summary,
            "checks": [
                {
                    "key": check.key,
                    "status": check.status,
                    "message": check.message,
                    "detail": check.detail,
                }
                for check in checks
            ],
        }

        if as_json:
            click.echo(json.dumps(payload, indent=2))
        else:
            for check in checks:
                label = check.status.upper()
                click.echo(f"[{label}] {check.key}: {check.message}")
                if check.status != "pass" and check.detail:
                    click.echo(f"       {check.detail}")
            click.echo(
                f"Summary: {summary['total']} checks, "
                f"{summary['failures']} failures, {summary['warnings']} warnings."
            )

        if summary["failures"] or (warnings_as_errors and summary["warnings"]):
            raise click.ClickException("Production readiness checks failed.")

    @app.cli.command("backup-verify")
    @click.option("--name", help="Backup filename under the configured local backup directory.")
    @click.option("--path", "backup_path", type=click.Path(exists=True, dir_okay=False), help="Explicit backup zip path.")
    @click.option("--json", "as_json", is_flag=True, help="Print machine-readable JSON.")
    def backup_verify_command(name=None, backup_path=None, as_json=False):
        """Verify a HaradiBots backup archive manifest and checksums."""
        from app.routes.admin import _safe_backup_path, _verify_backup_zip

        if backup_path:
            target = Path(backup_path).resolve()
        elif name:
            target = _safe_backup_path(name)
        else:
            raise click.ClickException("Pass --name local-backup.zip or --path C:\\path\\backup.zip.")
        if not target:
            raise click.ClickException("Backup archive was not found or path is not allowed.")

        result = _verify_backup_zip(target)
        if as_json:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            manifest = result.get("manifest") or {}
            click.echo(f"Backup: {target.name}")
            click.echo(f"Status: {'ok' if result['ok'] else 'failed'}")
            if manifest:
                click.echo(f"Created: {manifest.get('created_at')}")
                click.echo(f"Alembic: {manifest.get('alembic_revision') or 'unknown'}")
                click.echo(f"Files: {manifest.get('file_count', 0)}")
                click.echo(f"Bytes: {manifest.get('total_size', 0)}")
            for warning in result.get("warnings", []):
                click.echo(f"Warning: {warning}")
            for error in result.get("errors", []):
                click.echo(f"Error: {error}")
        if not result["ok"]:
            raise click.ClickException("Backup verification failed.")

    @app.cli.command("backup-drill")
    @click.option("--skip-database", is_flag=True, help="Do not request a database dump/copy.")
    @click.option("--skip-uploads", is_flag=True, help="Do not include uploaded files.")
    @click.option("--skip-logs", is_flag=True, help="Do not include logs/email outbox.")
    @click.option("--upload-cloud", is_flag=True, help="Upload the verified archive to configured Supabase backup storage.")
    @click.option("--json", "as_json", is_flag=True, help="Print machine-readable JSON.")
    def backup_drill_command(skip_database=False, skip_uploads=False, skip_logs=False, upload_cloud=False, as_json=False):
        """Create a backup archive, verify it, and optionally upload it to cloud storage."""
        from app.routes.admin import _create_backup_zip, _upload_backup_to_supabase, _verify_backup_zip

        zip_path = _create_backup_zip(
            include_database=not skip_database,
            include_uploads=not skip_uploads,
            include_logs=not skip_logs,
        )
        verification = _verify_backup_zip(zip_path)
        cloud = {"requested": bool(upload_cloud), "uploaded": False, "message": ""}
        if verification["ok"] and upload_cloud:
            try:
                uploaded, message = _upload_backup_to_supabase(zip_path)
                cloud.update({"uploaded": bool(uploaded), "message": message or ""})
            except Exception as exc:
                cloud.update({"uploaded": False, "message": f"{exc.__class__.__name__}: {exc}"})

        manifest = verification.get("manifest") or {}
        payload = {
            "ok": bool(verification["ok"] and (not upload_cloud or cloud["uploaded"])),
            "path": str(zip_path),
            "name": zip_path.name,
            "size": zip_path.stat().st_size if zip_path.exists() else 0,
            "verification": verification,
            "cloud": cloud,
            "summary": {
                "file_count": manifest.get("file_count", 0),
                "total_size": manifest.get("total_size", 0),
                "database_dump_present": manifest.get("database", {}).get("dump_present"),
                "alembic_revision": manifest.get("alembic_revision"),
            },
        }

        if as_json:
            click.echo(json.dumps(payload, indent=2, default=str))
        else:
            click.echo(f"Backup: {payload['name']}")
            click.echo(f"Path: {payload['path']}")
            click.echo(f"Status: {'ok' if payload['ok'] else 'failed'}")
            click.echo(f"Files: {payload['summary']['file_count']}")
            click.echo(f"Bytes: {payload['summary']['total_size']}")
            click.echo(f"Database dump: {'yes' if payload['summary']['database_dump_present'] else 'no'}")
            if cloud["requested"]:
                click.echo(f"Cloud upload: {'ok' if cloud['uploaded'] else 'failed'}")
                if cloud["message"]:
                    click.echo(f"Cloud message: {cloud['message']}")
            for warning in verification.get("warnings", []):
                click.echo(f"Warning: {warning}")
            for error in verification.get("errors", []):
                click.echo(f"Error: {error}")

        if not verification["ok"]:
            raise click.ClickException("Backup drill failed verification.")
        if upload_cloud and not cloud["uploaded"]:
            raise click.ClickException("Backup drill cloud upload failed.")

    @app.cli.command("smoke-check")
    @click.option("--base-url", help="Optional deployed base URL. Defaults to the local Flask app test client.")
    @click.option("--iterations", default=1, show_default=True, type=int, help="Requests per target.")
    @click.option("--timeout", default=10, show_default=True, type=float, help="External request timeout in seconds.")
    @click.option("--max-p95-ms", default=1000, show_default=True, type=float, help="Maximum p95 latency per target.")
    @click.option("--json", "as_json", is_flag=True, help="Print machine-readable JSON.")
    def smoke_check_command(base_url=None, iterations=1, timeout=10, max_p95_ms=1000, as_json=False):
        """Run lightweight route smoke and latency checks."""
        from app.services.smoke import run_smoke_targets, smoke_summary

        if not base_url:
            prepare_internal_test_schema()
        results = run_smoke_targets(
            app=None if base_url else app,
            base_url=base_url,
            iterations=iterations,
            timeout=timeout,
            max_p95_ms=max_p95_ms,
        )
        summary = smoke_summary(results)
        payload = {
            "summary": summary,
            "results": [
                {
                    "path": result.path,
                    "ok": result.ok,
                    "expected": result.expected,
                    "statuses": result.statuses,
                    "durations_ms": result.durations_ms,
                    "p95_ms": result.p95_ms,
                    "error": result.error,
                }
                for result in results
            ],
        }

        if as_json:
            click.echo(json.dumps(payload, indent=2, default=str))
        else:
            for result in results:
                status = "ok" if result.ok else "failed"
                click.echo(
                    f"{status} {result.path} statuses={result.statuses} "
                    f"p95={result.p95_ms}ms expected={result.expected}"
                )
                if result.error:
                    click.echo(f"  error: {result.error}")
            click.echo(f"Summary: {summary['total']} targets, {summary['failures']} failures.")

        if summary["failures"]:
            raise click.ClickException("Smoke checks failed.")

    @app.cli.command("load-check")
    @click.option("--base-url", help="Optional deployed base URL. Defaults to the local Flask app test client.")
    @click.option("--requests-per-target", default=10, show_default=True, type=int, help="Requests per route target.")
    @click.option("--concurrency", default=4, show_default=True, type=int, help="Concurrent workers per target.")
    @click.option("--timeout", default=10, show_default=True, type=float, help="External request timeout in seconds.")
    @click.option("--max-p95-ms", default=1500, show_default=True, type=float, help="Maximum p95 latency per target.")
    @click.option("--target", "target_paths", multiple=True, help="Limit checks to a route path. May be passed multiple times.")
    @click.option("--json", "as_json", is_flag=True, help="Print machine-readable JSON.")
    def load_check_command(base_url=None, requests_per_target=10, concurrency=4, timeout=10, max_p95_ms=1500, target_paths=(), as_json=False):
        """Run a small concurrent route load regression check."""
        from app.services.smoke import DEFAULT_SMOKE_TARGETS
        from app.services.load import load_summary, run_load_targets

        if not base_url:
            prepare_internal_test_schema()
        targets = None
        if target_paths:
            by_path = {target["path"]: target for target in DEFAULT_SMOKE_TARGETS}
            targets = [by_path.get(path, {"path": path, "expected": {200}}) for path in target_paths]

        results = run_load_targets(
            app=None if base_url else app,
            base_url=base_url,
            requests_per_target=requests_per_target,
            concurrency=concurrency,
            timeout=timeout,
            max_p95_ms=max_p95_ms,
            targets=targets,
        )
        summary = load_summary(results)
        payload = {
            "summary": summary,
            "results": [
                {
                    "path": result.path,
                    "ok": result.ok,
                    "expected": result.expected,
                    "requests": result.requests,
                    "concurrency": result.concurrency,
                    "statuses": result.statuses,
                    "errors": result.errors,
                    "min_ms": result.min_ms,
                    "avg_ms": result.avg_ms,
                    "p50_ms": result.p50_ms,
                    "p95_ms": result.p95_ms,
                    "max_ms": result.max_ms,
                    "duration_ms": result.duration_ms,
                    "rps": result.rps,
                }
                for result in results
            ],
        }

        if as_json:
            click.echo(json.dumps(payload, indent=2, default=str))
        else:
            for result in results:
                status = "ok" if result.ok else "failed"
                click.echo(
                    f"{status} {result.path} requests={result.requests} concurrency={result.concurrency} "
                    f"statuses={result.statuses} p95={result.p95_ms}ms rps={result.rps}"
                )
                for error in result.errors:
                    click.echo(f"  error: {error}")
            click.echo(
                f"Summary: {summary['total']} targets, {summary['failures']} failures, "
                f"{summary['completed_requests']}/{summary['total_requests']} completed, "
                f"aggregate_rps={summary['aggregate_rps']}."
            )

        if summary["failures"]:
            raise click.ClickException("Load checks failed.")

    @app.cli.command("email-check")
    @click.option("--to", "to_email", help="Send a real test email to this address after printing config.")
    @click.option(
        "--backend",
        type=click.Choice(["auto", "smtp", "backup_smtp", "resend", "sendgrid", "file"]),
        help="Temporarily test one backend without editing environment variables.",
    )
    def email_check_command(to_email=None, backend=None):
        """Print sanitized email config and optionally send a test email."""
        from app.utils.emailer import send_email

        if backend:
            app.config["EMAIL_BACKEND"] = backend

        def redacted_email(value):
            value = value or ""
            if "@" not in value:
                return "<empty>" if not value else "<set>"
            local, domain = value.rsplit("@", 1)
            return f"{local[:1]}***@{domain}"

        keys = [
            "EMAIL_BACKEND",
            "EMAIL_DELIVERY_ORDER",
            "EMAIL_FILE_FALLBACK",
            "EMAIL_ASYNC",
            "MAIL_SERVER",
            "MAIL_PORT",
            "MAIL_USE_TLS",
            "MAIL_USE_SSL",
            "MAIL_FORCE_IPV4",
            "MAIL_DEFAULT_SENDER",
        ]
        for key in keys:
            value = app.config.get(key)
            if key.endswith("_FROM") or key.endswith("_SENDER"):
                value = redacted_email(value)
            click.echo(f"{key}={value}")
        for key in ("MAIL_USERNAME", "MAIL_PASSWORD"):
            click.echo(f"{key}={'set' if app.config.get(key) else 'missing'}")

        if not to_email:
            click.echo("No email sent. Pass --to you@example.com to send a real test.")
            return

        ok = send_email(
            to_email,
            f"{app.config.get('APP_NAME', 'HaradiBots')} email check",
            "If you received this, transactional email delivery is working.",
        )
        if not ok:
            raise click.ClickException("Email delivery failed. Check service logs for backend errors.")
        click.echo(f"Test email sent to {to_email}.")


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
        app.logger.exception("Unhandled server error", extra={"request_id": getattr(g, "request_id", None)})
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
