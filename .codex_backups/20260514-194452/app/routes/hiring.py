"""Hiring ecosystem blueprint — job board, talent search, applications."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Job, Company, JobApplication, JobSave, User

hiring_bp = Blueprint("hiring", __name__)


@hiring_bp.get("/hiring")
def index():
    page = request.args.get("page", 1, type=int)
    category = request.args.get("category", "")
    job_type = request.args.get("type", "")
    work_mode = request.args.get("mode", "")
    query = request.args.get("q", "").strip()

    q = Job.query.filter_by(status="active")
    if category:
        q = q.filter_by(category=category)
    if job_type:
        q = q.filter_by(job_type=job_type)
    if work_mode:
        q = q.filter_by(work_mode=work_mode)
    if query:
        q = q.filter(Job.title.ilike(f"%{query}%"))

    jobs = q.order_by(Job.created_at.desc()).paginate(page=page, per_page=12, error_out=False)

    categories = ["robotics", "ai-ml", "web", "mobile", "devops", "data-science", "embedded", "startup", "other"]
    job_types = ["full-time", "part-time", "contract", "internship", "freelance"]
    work_modes = ["remote", "onsite", "hybrid"]

    return render_template(
        "hiring/index.html",
        jobs=jobs,
        categories=categories,
        job_types=job_types,
        work_modes=work_modes,
        current_category=category,
        current_type=job_type,
        current_mode=work_mode,
        query=query,
    )


@hiring_bp.get("/hiring/<slug>")
def job_detail(slug):
    job = Job.query.filter_by(slug=slug, status="active").first_or_404()
    job.views_count = (job.views_count or 0) + 1
    db.session.commit()
    has_applied = False
    is_saved = False
    if current_user.is_authenticated:
        has_applied = JobApplication.query.filter_by(job_id=job.id, user_id=current_user.id).first() is not None
        is_saved = JobSave.query.filter_by(job_id=job.id, user_id=current_user.id).first() is not None
    return render_template("hiring/job_detail.html", job=job, has_applied=has_applied, is_saved=is_saved)


@hiring_bp.post("/hiring/apply/<int:job_id>")
@login_required
def apply_job(job_id):
    job = Job.query.get_or_404(job_id)
    existing = JobApplication.query.filter_by(job_id=job.id, user_id=current_user.id).first()
    if existing:
        flash("You already applied to this job.", "warning")
        return redirect(url_for("hiring.job_detail", slug=job.slug))
    app = JobApplication(
        job_id=job.id,
        user_id=current_user.id,
        cover_note=request.form.get("cover_note", "").strip(),
        resume_url=current_user.resume_url,
    )
    job.applications_count = (job.applications_count or 0) + 1
    db.session.add(app)
    db.session.commit()
    flash("Application submitted!", "success")
    return redirect(url_for("hiring.job_detail", slug=job.slug))


@hiring_bp.post("/hiring/save/<int:job_id>")
@login_required
def save_job(job_id):
    job = Job.query.get_or_404(job_id)
    existing = JobSave.query.filter_by(job_id=job.id, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return {"saved": False}
    db.session.add(JobSave(job_id=job.id, user_id=current_user.id))
    db.session.commit()
    return {"saved": True}


@hiring_bp.get("/hiring/talent")
def talent_search():
    page = request.args.get("page", 1, type=int)
    query = request.args.get("q", "").strip()
    skill = request.args.get("skill", "").strip()

    q = User.query.filter_by(active=True, is_verified=True, open_to_work=True)
    if query:
        q = q.filter(
            db.or_(
                User.username.ilike(f"%{query}%"),
                User.full_name.ilike(f"%{query}%"),
                User.headline.ilike(f"%{query}%"),
            )
        )
    if skill:
        q = q.filter(User.skills.ilike(f"%{skill}%"))

    users = q.order_by(User.xp_total.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("hiring/talent.html", users=users, query=query, skill=skill)
