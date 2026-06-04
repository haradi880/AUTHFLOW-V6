"""Versioned JSON API with consistent envelopes and pagination."""

from flask import Blueprint, jsonify, request
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

from app.extensions import db
from app.models import Blog, Job, Project, User
from app.services.search import search_all
from app.utils.rate_limit import rate_limit

api_v1_bp = Blueprint("api_v1", __name__)


def ok(data=None, meta=None, status=200):
    return jsonify({"ok": True, "data": data if data is not None else {}, "meta": meta or {}}), status


def fail(message, status=400, code="bad_request", details=None):
    return jsonify({"ok": False, "error": {"code": code, "message": message, "details": details or {}}}), status


def pagination_args(default=20, maximum=100):
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(maximum, max(1, request.args.get("per_page", default, type=int)))
    return page, per_page


def pagination_meta(pagination):
    return {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "total": pagination.total,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }


@api_v1_bp.errorhandler(HTTPException)
def handle_http_error(error):
    return fail(error.description or error.name, error.code or 500, error.name.lower().replace(" ", "_"))


@api_v1_bp.errorhandler(Exception)
def handle_unexpected_error(error):
    return fail("Unexpected server error.", 500, "internal_error")


@api_v1_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return ok({"status": "healthy" if db_ok else "degraded", "database": db_ok})


@api_v1_bp.get("/jobs")
@rate_limit(max_calls=120, window_seconds=60, scope="api-v1-jobs", methods={"GET"})
def jobs():
    page, per_page = pagination_args()
    query_text = request.args.get("q", "").strip()
    work_mode = request.args.get("mode", "").strip()
    category = request.args.get("category", "").strip()
    query = Job.query.filter_by(status="active")
    if query_text:
        pattern = f"%{query_text}%"
        query = query.filter(db.or_(Job.title.ilike(pattern), Job.description.ilike(pattern), Job.skills_required.ilike(pattern), Job.location.ilike(pattern)))
    if work_mode:
        query = query.filter(Job.work_mode == work_mode)
    if category:
        query = query.filter(Job.category == category)
    pagination = query.order_by(Job.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return ok(
        [
            {
                "id": job.id,
                "title": job.title,
                "slug": job.slug,
                "company": job.company.name if job.company else None,
                "location": job.location,
                "work_mode": job.work_mode,
                "job_type": job.job_type,
                "category": job.category,
                "applications_count": job.applications_count,
                "created_at": job.created_at.isoformat(),
            }
            for job in pagination.items
        ],
        pagination_meta(pagination),
    )


@api_v1_bp.get("/search")
@rate_limit(max_calls=120, window_seconds=60, scope="api-v1-search", methods={"GET"})
def search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return ok({"users": [], "blogs": [], "projects": [], "jobs": [], "tags": []}, {"query": q})
    results = search_all(q, limit=10)
    return ok(
        {
            "users": [{"username": user.username, "full_name": user.full_name, "headline": user.headline} for user in results["users"]],
            "blogs": [{"title": blog.title, "slug": blog.slug, "excerpt": blog.excerpt} for blog in results["blogs"]],
            "projects": [{"title": project.title, "slug": project.slug, "description": project.description[:180]} for project in results["projects"]],
            "jobs": [{"title": job.title, "slug": job.slug, "company": job.company.name if job.company else None} for job in results["jobs"]],
            "tags": [{"name": tag.name, "slug": tag.slug} for tag in results["tags"]],
        },
        {"query": q},
    )
