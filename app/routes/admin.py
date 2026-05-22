"""Admin Routes - Admin dashboard, moderation, backups, and user management."""

import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests
from flask import Blueprint, render_template, flash, redirect, request, url_for, current_app, send_file
from flask_login import current_user
from sqlalchemy.exc import ProgrammingError, OperationalError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import AuditLog, DonationIntent, Job, LoginEvent, LoginSession, Notification, SupportTicket, User, Blog, Project, Report
from app.utils.decorators import admin_required
from app.utils.audit import AuditEventType, audit_log

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/login')
def admin_login():
    flash('Sign in with an administrator account to continue.', 'info')
    return redirect(url_for('auth.login', next=url_for('admin.admin_dashboard')))


@admin_bp.route('/')
@admin_required
def admin_dashboard():
    users = User.query.order_by(User.created_at.desc()).all()
    total_users = User.query.count()
    total_admins = User.query.filter_by(is_admin=True).count()
    total_blogs = Blog.query.count()
    total_projects = Project.query.count()
    open_reports = Report.query.filter_by(status="open").count()
    active_jobs = Job.query.filter_by(status="active").count()
    failed_logins = LoginEvent.query.filter_by(success=False).count()
    queued_notifications = Notification.query.filter(Notification.email_status.in_(["pending", "queued", "failed"])).count()
    donation_intents = DonationIntent.query.count()
    review_blogs = Blog.query.filter_by(status="draft").order_by(Blog.updated_at.desc()).limit(25).all()
    review_projects = Project.query.filter_by(status="draft").order_by(Project.updated_at.desc()).limit(25).all()
    reports = Report.query.order_by(Report.created_at.desc()).limit(25).all()
    return render_template('dashboard/admin.html', users=users,
                         total_users=total_users, total_admins=total_admins,
                         total_blogs=total_blogs, total_projects=total_projects,
                         open_reports=open_reports, reports=reports,
                         active_jobs=active_jobs, failed_logins=failed_logins,
                         queued_notifications=queued_notifications,
                         donation_intents=donation_intents,
                         review_blogs=review_blogs, review_projects=review_projects)


@admin_bp.post('/users/<int:user_id>/toggle-active')
@admin_required
def toggle_user_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Admin accounts cannot be suspended from this panel.', 'error')
        return redirect(url_for('admin.admin_dashboard'))
    user.active = not user.active
    if not user.active:
        LoginSession.query.filter_by(user_id=user.id, revoked_at=None).update(
            {"revoked_at": datetime.utcnow(), "is_current": False},
            synchronize_session=False,
        )
    audit_log(
        AuditEventType.USER_UNSUSPENDED if user.active else AuditEventType.USER_SUSPENDED,
        description=f"@{user.username} was {'restored' if user.active else 'suspended'} by admin.",
        target_id=user.id,
        target_type="user",
    )
    db.session.commit()
    flash(f"@{user.username} is now {'active' if user.active else 'suspended'}.", 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.post('/reports/<int:report_id>/status')
@admin_required
def update_report_status(report_id):
    report = Report.query.get_or_404(report_id)
    status = request.form.get('status')
    if status not in {'open', 'reviewing', 'resolved', 'dismissed'}:
        flash('Invalid report status.', 'error')
        return redirect(url_for('admin.admin_dashboard'))
    report.status = status
    db.session.commit()
    flash('Report status updated.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.post('/content/blogs/<int:blog_id>/status')
@admin_required
def update_blog_status(blog_id):
    blog = Blog.query.get_or_404(blog_id)
    status = request.form.get('status')
    if status not in {'draft', 'published'}:
        flash('Invalid blog status.', 'error')
        return redirect(url_for('admin.admin_dashboard'))
    blog.status = status
    db.session.commit()
    flash('Blog status updated.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.post('/content/projects/<int:project_id>/status')
@admin_required
def update_project_status(project_id):
    project = Project.query.get_or_404(project_id)
    status = request.form.get('status')
    if status not in {'draft', 'published'}:
        flash('Invalid project status.', 'error')
        return redirect(url_for('admin.admin_dashboard'))
    project.status = status
    db.session.commit()
    flash('Project status updated.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.get('/logs')
@admin_required
def logs():
    event_type = request.args.get('event_type', '').strip()
    actor = request.args.get('actor', '').strip()
    ip = request.args.get('ip', '').strip()
    query = AuditLog.query
    if event_type:
        query = query.filter(AuditLog.event_type.ilike(f'%{event_type}%'))
    if actor:
        query = query.filter(AuditLog.actor_username.ilike(f'%{actor}%'))
    if ip:
        query = query.filter(AuditLog.ip_address.ilike(f'%{ip}%'))
    audit_logs = query.order_by(AuditLog.created_at.desc()).limit(100).all()
    login_events = LoginEvent.query.order_by(LoginEvent.created_at.desc()).limit(50).all()
    donations = DonationIntent.query.order_by(DonationIntent.created_at.desc()).limit(25).all()
    try:
        support_tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).limit(30).all()
    except (ProgrammingError, OperationalError):
        db.session.rollback()
        current_app.logger.exception("support_tickets table is missing; run database migrations")
        support_tickets = []
        flash("Support ticket table is not ready yet. Run database migrations, then refresh this page.", "warning")
    return render_template(
        'dashboard/logs.html',
        audit_logs=audit_logs,
        login_events=login_events,
        donations=donations,
        support_tickets=support_tickets,
        event_type=event_type,
        actor=actor,
        ip=ip,
    )


@admin_bp.post('/support-tickets/<int:ticket_id>/status')
@admin_required
def update_support_ticket_status(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    status = request.form.get('status')
    if status not in {'open', 'reviewing', 'waiting-user', 'resolved', 'closed'}:
        flash('Invalid support ticket status.', 'error')
        return redirect(url_for('admin.logs'))
    ticket.status = status
    ticket.admin_note = request.form.get('admin_note', '').strip()[:1000]
    ticket.handled_by_id = current_user.id
    if status in {'resolved', 'closed'}:
        ticket.resolved_at = datetime.utcnow()
    db.session.commit()
    flash('Support ticket updated.', 'success')
    return redirect(url_for('admin.logs'))


@admin_bp.get('/backup')
@admin_required
def backup_index():
    """Admin backup page with recent local archives."""
    return render_template(
        'dashboard/backup.html',
        backups=_list_backup_files(),
        supabase_ready=bool(current_app.config.get('SUPABASE_URL') and current_app.config.get('SUPABASE_KEY')),
        backup_bucket=current_app.config.get('BACKUP_STORAGE_BUCKET', 'backups'),
    )


def _project_root():
    return Path(current_app.root_path).resolve().parent


def _backup_dir():
    path = Path(current_app.config.get('UPLOAD_FOLDER', 'uploads'))
    if not path.is_absolute():
        path = _project_root() / path
    backup_path = path / 'backups'
    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path.resolve()


def _list_backup_files():
    backups = []
    for path in sorted(_backup_dir().glob('*.zip'), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        backups.append({
            'name': path.name,
            'size': stat.st_size,
            'created_at': datetime.fromtimestamp(stat.st_mtime),
        })
    return backups


def _safe_backup_path(name):
    safe_name = secure_filename(name or '')
    if not safe_name or safe_name != name or not safe_name.endswith('.zip'):
        return None
    candidate = (_backup_dir() / safe_name).resolve()
    if candidate.parent != _backup_dir() or not candidate.is_file():
        return None
    return candidate


def _write_database_dump(temp_dir):
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    db_dir = Path(temp_dir) / 'database'
    db_dir.mkdir(parents=True, exist_ok=True)

    if db_uri.startswith('sqlite:///'):
        sqlite_path = Path(db_uri.replace('sqlite:///', '', 1))
        if sqlite_path.exists():
            target = db_dir / sqlite_path.name
            shutil.copy2(sqlite_path, target)
            return target
        return None

    if db_uri and not db_uri.startswith('sqlite'):
        pg_dump = shutil.which('pg_dump')
        if not pg_dump:
            current_app.logger.warning('pg_dump is not available; database dump skipped')
            return None
        dump_file = db_dir / 'postgres_dump.sql'
        subprocess.run([pg_dump, '--dbname=' + db_uri, '-f', str(dump_file)], check=True, timeout=120)
        return dump_file

    return None


def _add_path_to_zip(zf, path, project_root, backup_dir, exclude_self):
    path = Path(path).resolve()
    if not path.exists():
        return
    if path.is_file():
        if exclude_self and path == exclude_self:
            return
        zf.write(path, path.relative_to(project_root).as_posix() if path.is_relative_to(project_root) else path.name)
        return

    for root, dirs, files in os.walk(path):
        root_path = Path(root).resolve()
        dirs[:] = [name for name in dirs if (root_path / name).resolve() != backup_dir]
        for filename in files:
            full = (root_path / filename).resolve()
            if exclude_self and full == exclude_self:
                continue
            try:
                arcname = full.relative_to(project_root).as_posix()
            except ValueError:
                arcname = full.name
            zf.write(full, arcname)


def _create_backup_zip(include_database=True, include_uploads=True, include_logs=True):
    project_root = _project_root()
    backup_dir = _backup_dir()
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    out_path = backup_dir / f"haradi_backup_{timestamp}.zip"
    temp_dir = tempfile.mkdtemp(prefix='haradi-backup-')
    included = []

    try:
        if include_database:
            try:
                dump_path = _write_database_dump(temp_dir)
                if dump_path:
                    included.append(dump_path)
            except Exception:
                current_app.logger.exception('Database dump failed; continuing with file backup')

        for folder_name, enabled in (
            ('uploads', include_uploads),
            ('instance', True),
            ('migrations', True),
            ('logs', include_logs),
        ):
            if enabled:
                included.append(project_root / folder_name)

        manifest = Path(temp_dir) / 'backup_manifest.txt'
        manifest.write_text(
            '\n'.join([
                f"created_at={datetime.utcnow().isoformat()}Z",
                f"app_name={current_app.config.get('APP_NAME', 'AUTHFLOW')}",
                f"database_included={bool(include_database)}",
                f"uploads_included={bool(include_uploads)}",
                f"logs_included={bool(include_logs)}",
            ]),
            encoding='utf-8',
        )
        included.append(manifest)

        with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for item in included:
                _add_path_to_zip(zf, item, project_root, backup_dir, out_path)
        _prune_old_backups()
        return out_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _prune_old_backups():
    keep = int(current_app.config.get('BACKUP_KEEP_LOCAL', 20) or 20)
    if keep < 1:
        return
    backups = sorted(_backup_dir().glob('*.zip'), key=lambda item: item.stat().st_mtime, reverse=True)
    for old_backup in backups[keep:]:
        try:
            old_backup.unlink()
        except OSError:
            current_app.logger.warning('Could not prune backup %s', old_backup)


def _upload_backup_to_supabase(path):
    supa_url = (current_app.config.get('SUPABASE_URL') or '').rstrip('/')
    supa_key = current_app.config.get('SUPABASE_KEY')
    bucket = current_app.config.get('BACKUP_STORAGE_BUCKET', 'backups')
    if not supa_url or not supa_key:
        return False, 'Supabase URL/key is not configured.'

    upload_endpoint = f"{supa_url}/storage/v1/object/{bucket}/{path.name}"
    headers = {
        'Authorization': f'Bearer {supa_key}',
        'apikey': supa_key,
        'x-upsert': 'true',
        'content-type': 'application/zip',
    }
    with path.open('rb') as file_handle:
        response = requests.post(upload_endpoint, headers=headers, data=file_handle, timeout=90)
    if response.status_code in (200, 201):
        return True, ''
    return False, f"Supabase upload failed with HTTP {response.status_code}: {response.text[:200]}"


@admin_bp.post('/backup/create')
@admin_required
def backup_create():
    """Create a local backup and optionally upload it to configured Supabase Storage."""
    try:
        zip_path = _create_backup_zip(
            include_database=request.form.get('include_database') == 'on',
            include_uploads=request.form.get('include_uploads') == 'on',
            include_logs=request.form.get('include_logs') == 'on',
        )
    except Exception as e:
        current_app.logger.exception('Failed to create backup')
        flash('Failed to create backup: ' + str(e), 'error')
        return redirect(url_for('admin.backup_index'))

    uploaded = False
    if request.form.get('upload_cloud') == 'on':
        try:
            uploaded, message = _upload_backup_to_supabase(zip_path)
            if not uploaded:
                flash(message, 'warning')
        except Exception:
            current_app.logger.exception('Supabase upload failed')
            flash('Backup was created locally, but cloud upload failed.', 'warning')

    flash(f"Backup created: {zip_path.name}" + (' and uploaded to cloud.' if uploaded else ''), 'success')
    return redirect(url_for('admin.backup_index'))


@admin_bp.post('/backup/upload')
@admin_required
def backup_upload():
    """Upload an existing local backup archive to configured Supabase Storage."""
    path = _safe_backup_path(request.form.get('name'))
    if not path:
        flash('Backup not found.', 'error')
        return redirect(url_for('admin.backup_index'))
    try:
        uploaded, message = _upload_backup_to_supabase(path)
    except Exception:
        current_app.logger.exception('Supabase upload failed')
        uploaded, message = False, 'Cloud upload failed.'
    flash(f'{path.name} uploaded to cloud.' if uploaded else message, 'success' if uploaded else 'error')
    return redirect(url_for('admin.backup_index'))


@admin_bp.get('/backup/download')
@admin_required
def backup_download():
    """Download a backup file by name (query param `name`)."""
    path = _safe_backup_path(request.args.get('name'))
    if not path:
        flash('Backup not found.', 'error')
        return redirect(url_for('admin.backup_index'))
    return send_file(path, as_attachment=True)
