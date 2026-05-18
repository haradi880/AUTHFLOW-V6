"""API Routes - JWT-based authentication and public content API."""

from datetime import datetime, timedelta

import jwt
from flask import current_app
from flask import Blueprint, jsonify, request

from app.models import Blog, Project, User
from app.services.auth import authenticate_user, normalize_email

api_bp = Blueprint('api', __name__)


def blog_payload(blog):
    return {
        "title": blog.title,
        "slug": blog.slug,
        "excerpt": blog.excerpt,
        "reading_time": blog.reading_time,
        "views_count": blog.views_count,
        "likes_count": blog.likes_count,
        "author": blog.author.username if blog.author else None,
        "tags": [tag.name for tag in blog.tags],
        "published_at": blog.published_at.isoformat() if blog.published_at else None,
    }


def project_payload(project):
    return {
        "title": project.title,
        "slug": project.slug,
        "description": project.description,
        "github_url": project.github_url,
        "demo_url": project.demo_url,
        "stars_count": project.stars_count,
        "author": project.author.username if project.author else None,
        "tech_stack": [tag.name for tag in project.tags],
        "created_at": project.created_at.isoformat(),
    }


def user_payload(user):
    progress = user.xp_progress
    return {
        "username": user.username,
        "full_name": user.full_name,
        "headline": user.headline,
        "bio": user.bio,
        "skills": user.get_skills_list(),
        "followers_count": user.followers_count(),
        "following_count": user.following_count(),
        "profile_views_count": user.profile_views_count or 0,
        "xp_total": user.xp_total or 0,
        "level": progress["level"],
        "xp_progress": progress,
    }

@api_bp.route('/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get('email', ''))
    password = data.get('password', '')
    
    user, error = authenticate_user(email, password)
    
    if user and not error:
        # Create JWT token
        token = jwt.encode({
            'user_id': user.id,
            'email': user.email,
            'exp': datetime.utcnow() + timedelta(hours=current_app.config['JWT_EXPIRATION_HOURS'])
        }, current_app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({'success': True, 'token': token, 'user': {'username': user.username, 'email': user.email}})
    
    return jsonify({'success': False, 'message': error or 'Invalid credentials'}), 401

@api_bp.route('/user', methods=['GET'])
def api_user():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    try:
        data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(data['user_id'])
        if user and user.is_active:
            payload = user_payload(user)
            payload["email"] = user.email
            return jsonify(payload)
    except jwt.PyJWTError:
        current_app.logger.info("Invalid API token")
    return jsonify({'error': 'Invalid token'}), 401


@api_bp.get('/me/xp')
def api_my_xp():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    try:
        data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(data['user_id'])
        if user and user.is_active:
            return jsonify(user.xp_progress)
    except jwt.PyJWTError:
        current_app.logger.info("Invalid API token")
    return jsonify({'error': 'Invalid token'}), 401


@api_bp.get('/profiles')
def api_profiles():
    users = User.query.filter_by(active=True).order_by(User.created_at.desc()).limit(25).all()
    return jsonify([user_payload(user) for user in users])


@api_bp.get('/profiles/<username>')
def api_profile(username):
    user = User.query.filter_by(username=username, active=True).first_or_404()
    payload = user_payload(user)
    payload["blogs"] = [
        blog_payload(blog)
        for blog in Blog.query.filter_by(user_id=user.id, status="published").order_by(Blog.created_at.desc()).limit(10).all()
    ]
    payload["projects"] = [
        project_payload(project)
        for project in Project.query.filter_by(user_id=user.id, status="published").order_by(Project.created_at.desc()).limit(10).all()
    ]
    return jsonify(payload)


@api_bp.get('/blogs')
def api_blogs():
    blogs = Blog.query.filter_by(status="published").order_by(Blog.created_at.desc()).limit(25).all()
    return jsonify([blog_payload(blog) for blog in blogs])


@api_bp.get('/blogs/<slug>')
def api_blog(slug):
    blog = Blog.query.filter_by(slug=slug, status="published").first_or_404()
    payload = blog_payload(blog)
    payload["content"] = blog.content
    return jsonify(payload)


@api_bp.get('/projects')
def api_projects():
    projects = Project.query.filter_by(status="published").order_by(Project.created_at.desc()).limit(25).all()
    return jsonify([project_payload(project) for project in projects])


@api_bp.get('/projects/<slug>')
def api_project(slug):
    project = Project.query.filter_by(slug=slug, status="published").first_or_404()
    payload = project_payload(project)
    payload["gallery"] = [{"filename": image.filename, "caption": image.caption} for image in project.images.order_by("order").all()]
    return jsonify(payload)
