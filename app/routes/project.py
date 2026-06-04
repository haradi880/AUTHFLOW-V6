"""
Project Routes - Create, Read, Update, Delete projects.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload, load_only, selectinload

from app.extensions import db
from app.models import Project, ProjectImage, ProjectStar, Category, Tag
from app.services.content import generate_slug, sync_tags
from app.services.gamification import award_xp
from app.services.cache import public_response_cache
from app.utils.helpers import paginate_without_count, create_notification
from app.utils.uploads_secure import delete_file_secure, save_upload_secure
from app.utils.decorators import owner_required
from app.utils.rate_limit import rate_limit

# Create the blueprint
project_bp = Blueprint('project', __name__)


# ============================================================
# PROJECT LISTING (Feed)
# ============================================================

@project_bp.route('/projects')
@public_response_cache("projects-feed")
def projects_feed():
    """Display all published projects."""
    
    # Get filter parameters
    category = request.args.get('category')
    tag = request.args.get('tag')
    sort = request.args.get('sort', 'latest')
    page = request.args.get('page', 1, type=int)
    
    # Base query - only published projects
    query = Project.query.options(
        load_only(
            Project.id,
            Project.title,
            Project.slug,
            Project.description,
            Project.thumbnail,
            Project.github_url,
            Project.demo_url,
            Project.stars_count,
            Project.status,
            Project.created_at,
            Project.user_id,
            Project.category_id,
        ),
        joinedload(Project.author),
        joinedload(Project.category),
        selectinload(Project.tags),
    ).filter_by(status='published')
    
    # Apply category filter
    if category:
        category_id = db.session.query(Category.id).filter_by(slug=category).scalar()
        if category_id:
            query = query.filter_by(category_id=category_id)
    
    # Apply tag filter
    if tag:
        query = query.filter(Project.tags.any(Tag.slug == tag))
    
    # Apply sorting
    if sort == 'stars':
        query = query.order_by(Project.stars_count.desc())
    elif sort == 'trending':
        query = query.order_by(Project.stars_count.desc())
    else:  # latest
        query = query.order_by(Project.created_at.desc())
    
    # Paginate
    pagination = paginate_without_count(query, page)
    projects = pagination.items
    
    # Get categories and tags for filters
    categories = Category.query.options(load_only(Category.id, Category.name, Category.slug)).order_by(Category.name.asc()).all()
    trending_tags = Tag.query.options(load_only(Tag.id, Tag.name, Tag.slug)).order_by(Tag.name.asc()).limit(10).all()
    
    return render_template('feed/projects_feed.html',
                         projects=projects,
                         pagination=pagination,
                         categories=categories,
                         trending_tags=trending_tags)


# ============================================================
# PROJECT DETAIL PAGE
# ============================================================

@project_bp.route('/project/<slug>')
def project_detail(slug):
    """View a single project."""
    
    # Find the project
    project = Project.query.filter_by(slug=slug, status='published').first_or_404()
    
    # Get project images/gallery
    gallery = ProjectImage.query.filter_by(project_id=project.id)\
        .order_by(ProjectImage.order).all()
    
    # Get related projects (same category)
    related = Project.query.filter(
        Project.id != project.id,
        Project.status == 'published',
        Project.category_id == project.category_id
    ).limit(3).all()
    
    return render_template('content/project_detail.html',
                         project=project,
                         gallery=gallery,
                         related_projects=related,
                         is_starred=project.is_starred_by(current_user) if current_user.is_authenticated else False)


@project_bp.route('/project/<int:project_id>/star', methods=['POST'])
@login_required
@rate_limit(max_calls=60, window_seconds=300, scope="project-star")
def star_project(project_id):
    project = db.get_or_404(Project, project_id)
    existing = ProjectStar.query.filter_by(user_id=current_user.id, project_id=project.id).first()
    if existing:
        db.session.delete(existing)
        project.stars_count = max(0, project.stars_count - 1)
        db.session.commit()
        return {'status': 'unstarred', 'count': project.stars_count}

    star = ProjectStar(user_id=current_user.id, project_id=project.id)
    db.session.add(star)
    project.stars_count += 1
    db.session.commit()
    if project.user_id != current_user.id:
        award_xp(project.author, "receive_project_star", source=star)
        create_notification(
            user=project.author,
            action='star',
            message=f'{current_user.username} starred your project "{project.title}"',
            link=url_for('project.project_detail', slug=project.slug),
            from_user=current_user,
        )
    return {'status': 'starred', 'count': project.stars_count}


# ============================================================
# CREATE PROJECT
# ============================================================

@project_bp.route('/upload/project', methods=['GET', 'POST'])
@login_required
@rate_limit(max_calls=12, window_seconds=300, scope="project-upload")
def create_project():
    """Create a new project."""
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '')
        category_id = request.form.get('category_id', type=int)
        tags_str = request.form.get('tags', '')
        github_url = request.form.get('github_url', '').strip()
        demo_url = request.form.get('demo_url', '').strip()
        status = request.form.get('status', 'draft')
        
        # Generate unique slug
        slug = generate_slug(title, Project)
        
        # Create project
        project = Project(
            title=title,
            slug=slug,
            description=description,
            github_url=github_url,
            demo_url=demo_url,
            status=status,
            user_id=current_user.id,
            category_id=category_id
        )
        
        # Handle thumbnail
        if 'thumbnail' in request.files:
            file = request.files['thumbnail']
            if file.filename:
                filename, error = save_upload_secure(file, 'projects')
                if filename:
                    project.thumbnail = filename
                else:
                    flash(f'Thumbnail upload failed: {error}', 'error')
        
        # Handle gallery images
        if 'images' in request.files:
            files = request.files.getlist('images')
            for i, file in enumerate(files):
                if file.filename:
                    filename, error = save_upload_secure(file, 'projects')
                    if filename:
                        img = ProjectImage(
                            filename=filename,
                            order=i,
                            project=project
                        )
                        db.session.add(img)
                    else:
                        flash(f'Gallery image "{file.filename}" could not be saved: {error}', 'error')
        
        sync_tags(project, tags_str)
        
        db.session.add(project)
        db.session.commit()
        if project.status == 'published':
            award_xp(current_user, "publish_project", source=project)
        
        flash('Project created successfully!', 'success')
        return redirect(url_for('project.project_detail', slug=project.slug))
    
    # GET request - show form
    categories = Category.query.all()
    return render_template('content/upload_project.html', categories=categories)


# ============================================================
# EDIT PROJECT
# ============================================================

@project_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
@owner_required(Project)
@rate_limit(max_calls=20, window_seconds=300, scope="project-edit")
def edit_project(project_id):
    """Edit an existing project."""
    
    project = db.get_or_404(Project, project_id)
    
    if request.method == 'POST':
        project.title = request.form.get('title', '').strip()
        project.description = request.form.get('description', '')
        project.category_id = request.form.get('category_id', type=int)
        project.github_url = request.form.get('github_url', '').strip()
        project.demo_url = request.form.get('demo_url', '').strip()
        was_published = project.status == 'published'
        project.status = request.form.get('status', 'draft')
        
        # Handle thumbnail
        if 'thumbnail' in request.files:
            file = request.files['thumbnail']
            if file.filename:
                delete_file_secure(project.thumbnail, 'projects')
                filename, error = save_upload_secure(file, 'projects')
                if filename:
                    project.thumbnail = filename
                else:
                    flash(f'Thumbnail upload failed: {error}', 'error')
        
        # Handle new gallery images
        if 'images' in request.files:
            files = request.files.getlist('images')
            if files and files[0].filename:
                # Get current max order
                max_order = db.session.query(db.func.max(ProjectImage.order))\
                    .filter_by(project_id=project.id).scalar() or 0
                
                for i, file in enumerate(files):
                    if file.filename:
                        filename, error = save_upload_secure(file, 'projects')
                        if filename:
                            img = ProjectImage(
                                filename=filename,
                                order=max_order + i + 1,
                                project=project
                            )
                            db.session.add(img)
                        else:
                            flash(f'Gallery image "{file.filename}" could not be saved: {error}', 'error')
        
        sync_tags(project, request.form.get('tags', ''))
        
        db.session.commit()
        if project.status == 'published' and not was_published:
            award_xp(current_user, "publish_project", source=project)
        flash('Project updated successfully!', 'success')
        return redirect(url_for('project.project_detail', slug=project.slug))
    
    categories = Category.query.all()
    return render_template('content/upload_project.html',
                         project=project,
                         categories=categories,
                         gallery=project.images.order_by(ProjectImage.order).all(),
                         editing=True)


@project_bp.route('/project/image/<int:image_id>/delete', methods=['POST'])
@login_required
def delete_project_image(image_id):
    image = db.get_or_404(ProjectImage, image_id)
    project = image.project
    if project.user_id != current_user.id and not current_user.is_admin:
        flash('You can only edit your own project gallery.', 'error')
        return redirect(url_for('main.home'))
    delete_file_secure(image.filename, 'projects')
    db.session.delete(image)
    db.session.commit()
    flash('Gallery image removed.', 'success')
    return redirect(url_for('project.edit_project', project_id=project.id))


# ============================================================
# DELETE PROJECT
# ============================================================

@project_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
@owner_required(Project)
def delete_project(project_id):
    """Delete a project securely with audit trail."""
    from app.utils.password_confirm import confirm_password
    from app.utils.soft_delete import soft_delete
    from app.utils.audit import audit_log, AuditEventType
    
    project = db.get_or_404(Project, project_id)
    
    # Verify password for this sensitive operation
    password = request.form.get('password', '').strip()
    if not password or not confirm_password(password):
        flash('Invalid password. Deletion cancelled.', 'error')
        return redirect(url_for('project.project_detail', slug=project.slug))
    
    # Delete thumbnail and gallery images
    delete_file_secure(project.thumbnail, 'projects')
    for image in project.images.all():
        delete_file_secure(image.filename, 'projects')
    
    # Soft delete the project (keeps archived copy for recovery)
    if soft_delete(
        project,
        content_type='project',
        user_id=current_user.id,
        reason='User deletion',
        recovery_days=30
    ):
        flash('Project deleted successfully. You can recover it within 30 days.', 'success')
        audit_log(
            event_type=AuditEventType.CONTENT_DELETED,
            description=f"Deleted project: {project.title}",
            target_id=project_id,
            target_type='project',
            metadata={"slug": project.slug}
        )
    else:
        flash('Error deleting project. Please try again.', 'error')
    
    return redirect(url_for('main.home'))
