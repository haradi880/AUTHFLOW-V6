"""API Routes - JWT-based authentication and public content API."""

from datetime import datetime, timedelta
import uuid

import jwt
from flask import current_app
from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Blog, Project, User
from app.services.auth import authenticate_user, normalize_email
from app.utils.rate_limit import rate_limit

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


def _issue_token(user):
    now = datetime.utcnow()
    return jwt.encode(
        {
            "sub": str(user.id),
            "user_id": user.id,
            "email": user.email,
            "iss": current_app.config["JWT_ISSUER"],
            "aud": current_app.config["JWT_AUDIENCE"],
            "iat": now,
            "jti": uuid.uuid4().hex,
            "exp": now + timedelta(hours=current_app.config["JWT_EXPIRATION_HOURS"]),
        },
        current_app.config["SECRET_KEY"],
        algorithm="HS256",
    )


def _current_api_user():
    token = request.headers.get("Authorization", "").replace("Bearer ", "", 1).strip()
    if not token:
        return None
    try:
        data = jwt.decode(
            token,
            current_app.config["SECRET_KEY"],
            algorithms=["HS256"],
            audience=current_app.config["JWT_AUDIENCE"],
            issuer=current_app.config["JWT_ISSUER"],
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
        user = db.session.get(User, int(data["sub"]))
        return user if user and user.is_active else None
    except (jwt.PyJWTError, ValueError, TypeError):
        current_app.logger.info("Invalid API token")
        return None

@api_bp.route('/login', methods=['POST'])
@rate_limit(max_calls=10, window_seconds=300, scope="api-login")
def api_login():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get('email', ''))
    password = data.get('password', '')
    
    user, error = authenticate_user(email, password)
    
    if user and not error:
        token = _issue_token(user)
        
        return jsonify({'success': True, 'token': token, 'user': {'username': user.username, 'email': user.email}})
    
    return jsonify({'success': False, 'message': error or 'Invalid credentials'}), 401

@api_bp.route('/user', methods=['GET'])
@rate_limit(max_calls=120, window_seconds=60, scope="api-user", methods={"GET"})
def api_user():
    user = _current_api_user()
    if user:
        payload = user_payload(user)
        payload["email"] = user.email
        return jsonify(payload)
    return jsonify({'error': 'Invalid token'}), 401


@api_bp.get('/me/xp')
@rate_limit(max_calls=120, window_seconds=60, scope="api-me-xp", methods={"GET"})
def api_my_xp():
    user = _current_api_user()
    if user:
        return jsonify(user.xp_progress)
    return jsonify({'error': 'Invalid token'}), 401


@api_bp.get('/profiles')
@rate_limit(max_calls=120, window_seconds=60, scope="api-profiles", methods={"GET"})
def api_profiles():
    users = User.query.filter(User.active.is_(True)).order_by(User.created_at.desc()).limit(25).all()
    return jsonify([user_payload(user) for user in users])


@api_bp.get('/profiles/<username>')
@rate_limit(max_calls=120, window_seconds=60, scope="api-profile", methods={"GET"})
def api_profile(username):
    user = User.query.filter(User.username == username, User.active.is_(True)).first_or_404()
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
@rate_limit(max_calls=120, window_seconds=60, scope="api-blogs", methods={"GET"})
def api_blogs():
    blogs = Blog.query.filter_by(status="published").order_by(Blog.created_at.desc()).limit(25).all()
    return jsonify([blog_payload(blog) for blog in blogs])


@api_bp.get('/blogs/<slug>')
@rate_limit(max_calls=120, window_seconds=60, scope="api-blog", methods={"GET"})
def api_blog(slug):
    blog = Blog.query.filter_by(slug=slug, status="published").first_or_404()
    payload = blog_payload(blog)
    payload["content"] = blog.content
    return jsonify(payload)


@api_bp.get('/projects')
@rate_limit(max_calls=120, window_seconds=60, scope="api-projects", methods={"GET"})
def api_projects():
    projects = Project.query.filter_by(status="published").order_by(Project.created_at.desc()).limit(25).all()
    return jsonify([project_payload(project) for project in projects])


@api_bp.get('/projects/<slug>')
@rate_limit(max_calls=120, window_seconds=60, scope="api-project", methods={"GET"})
def api_project(slug):
    project = Project.query.filter_by(slug=slug, status="published").first_or_404()
    payload = project_payload(project)
    payload["gallery"] = [{"filename": image.filename, "caption": image.caption} for image in project.images.order_by("order").all()]
    return jsonify(payload)
