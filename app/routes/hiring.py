"""Hiring ecosystem blueprint: job board, talent search, applications."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Company, Job, JobApplication, JobSave, User
from app.services.content import generate_slug

hiring_bp = Blueprint("hiring", __name__)

CATEGORIES = ["robotics", "ai-ml", "web", "mobile", "devops", "data-science", "embedded", "startup", "other"]
JOB_TYPES = ["full-time", "part-time", "contract", "internship", "freelance"]
WORK_MODES = ["remote", "onsite", "hybrid"]
EXPERIENCE_LEVELS = ["entry", "mid", "senior", "lead"]


def _choice(value, allowed, default):
    return value if value in allowed else default


def _salary(value):
    try:
        amount = int(value or 0)
        return amount if amount > 0 else None
    except (TypeError, ValueError):
        return None


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

    return render_template(
        "hiring/index.html",
        jobs=jobs,
        categories=CATEGORIES,
        job_types=JOB_TYPES,
        work_modes=WORK_MODES,
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
    flash("Application submitted.", "success")
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


@hiring_bp.route("/hiring/post", methods=["GET", "POST"])
@hiring_bp.route("/upload/job", methods=["GET", "POST"])
@login_required
def post_job():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        company_name = request.form.get("company_name", "").strip()
        if len(title) < 3 or len(description) < 20 or len(company_name) < 2:
            flash("Add a job title, company name, and useful description.", "error")
            return render_template("hiring/post_job.html", categories=CATEGORIES, job_types=JOB_TYPES, work_modes=WORK_MODES, experience_levels=EXPERIENCE_LEVELS)

        company = Company.query.filter_by(name=company_name).first()
        if not company:
            company = Company(
                name=company_name,
                slug=generate_slug(company_name, Company),
                description=request.form.get("company_description", "").strip(),
                website=request.form.get("company_website", "").strip(),
                location=request.form.get("company_location", "").strip(),
                created_by_id=current_user.id,
            )
            db.session.add(company)
            db.session.flush()

        job = Job(
            title=title,
            slug=generate_slug(title, Job),
            description=description,
            job_type=_choice(request.form.get("job_type"), JOB_TYPES, "full-time"),
            work_mode=_choice(request.form.get("work_mode"), WORK_MODES, "remote"),
            category=_choice(request.form.get("category"), CATEGORIES, "other"),
            location=request.form.get("location", "").strip(),
            salary_min=_salary(request.form.get("salary_min")),
            salary_max=_salary(request.form.get("salary_max")),
            salary_currency=(request.form.get("salary_currency") or "USD").strip()[:10],
            experience_level=_choice(request.form.get("experience_level"), EXPERIENCE_LEVELS, "mid"),
            skills_required=request.form.get("skills_required", "").strip(),
            status=_choice(request.form.get("status"), {"active", "draft"}, "active"),
            company_id=company.id,
            posted_by_id=current_user.id,
        )
        current_user.is_recruiter = True
        db.session.add(job)
        db.session.commit()
        flash("Job post saved.", "success")
        if job.status == "active":
            return redirect(url_for("hiring.job_detail", slug=job.slug))
        return redirect(url_for("hiring.index"))

    return render_template("hiring/post_job.html", categories=CATEGORIES, job_types=JOB_TYPES, work_modes=WORK_MODES, experience_levels=EXPERIENCE_LEVELS)


@hiring_bp.post("/hiring/<int:job_id>/delete")
@login_required
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    company_owner_id = job.company.created_by_id if job.company else None
    if job.posted_by_id != current_user.id and company_owner_id != current_user.id and not current_user.is_admin:
        flash("You can only delete jobs you posted.", "error")
        return redirect(url_for("hiring.job_detail", slug=job.slug))
    db.session.delete(job)
    db.session.commit()
    flash("Job post deleted.", "success")
    return redirect(url_for("hiring.index"))


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
