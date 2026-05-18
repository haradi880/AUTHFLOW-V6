"""Admin Routes - Admin dashboard, moderation, and user management."""

from flask import Blueprint, render_template, flash, redirect, request, url_for
from app.extensions import db
from app.models import User, Blog, Project, Report
from app.utils.decorators import admin_required

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
    review_blogs = Blog.query.filter_by(status="draft").order_by(Blog.updated_at.desc()).limit(25).all()
    review_projects = Project.query.filter_by(status="draft").order_by(Project.updated_at.desc()).limit(25).all()
    reports = Report.query.order_by(Report.created_at.desc()).limit(25).all()
    return render_template('dashboard/admin.html', users=users,
                         total_users=total_users, total_admins=total_admins,
                         total_blogs=total_blogs, total_projects=total_projects,
                         open_reports=open_reports, reports=reports,
                         review_blogs=review_blogs, review_projects=review_projects)


@admin_bp.post('/users/<int:user_id>/toggle-active')
@admin_required
def toggle_user_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Admin accounts cannot be suspended from this panel.', 'error')
        return redirect(url_for('admin.admin_dashboard'))
    user.active = not user.active
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
