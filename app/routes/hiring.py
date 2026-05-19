"""Hiring ecosystem blueprint: job board, talent search, applications."""

from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Company, Job, JobApplication, JobSave, User
from app.services.content import generate_slug
from app.services.notifications import create_notification

hiring_bp = Blueprint("hiring", __name__)

CATEGORIES = ["robotics", "ai-ml", "web", "mobile", "devops", "data-science", "embedded", "startup", "other"]
JOB_TYPES = ["full-time", "part-time", "contract", "internship", "freelance"]
WORK_MODES = ["remote", "onsite", "hybrid"]
EXPERIENCE_LEVELS = ["entry", "mid", "senior", "lead"]
APPLICATION_STATUSES = ["applied", "reviewed", "shortlisted", "interview", "offer", "rejected", "hired", "withdrawn"]


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

    q = Job.query.filter_by(status="active").join(Company)
    if category:
        q = q.filter_by(category=category)
    if job_type:
        q = q.filter_by(job_type=job_type)
    if work_mode:
        q = q.filter_by(work_mode=work_mode)
    if query:
        search = f"%{query}%"
        q = q.filter(
            db.or_(
                Job.title.ilike(search),
                Job.description.ilike(search),
                Job.skills_required.ilike(search),
                Company.name.ilike(search),
                Job.location.ilike(search),
            )
        )

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
    application = None
    is_saved = False
    if current_user.is_authenticated:
        application = JobApplication.query.filter_by(job_id=job.id, user_id=current_user.id).first()
        has_applied = application is not None
        is_saved = JobSave.query.filter_by(job_id=job.id, user_id=current_user.id).first() is not None
    return render_template("hiring/job_detail.html", job=job, has_applied=has_applied, application=application, is_saved=is_saved)


@hiring_bp.post("/hiring/apply/<int:job_id>")
@login_required
def apply_job(job_id):
    job = Job.query.get_or_404(job_id)
    if job.status != "active":
        flash("This job is no longer accepting applications.", "warning")
        return redirect(url_for("hiring.job_detail", slug=job.slug))
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
    db.session.flush()
    applicant_link = url_for("hiring.my_applications", _external=False)
    recruiter_link = url_for("hiring.job_applications", job_id=job.id, _external=False)
    create_notification(
        user=current_user,
        action="job_application_submitted",
        message=f"Your application for {job.title} at {job.company.name if job.company else 'the company'} was submitted.",
        link=applicant_link,
        from_user=job.posted_by,
        commit=False,
        priority="high",
        entity_type="job_application",
        entity_id=app.id,
    )
    if job.posted_by and job.posted_by_id != current_user.id:
        create_notification(
            user=job.posted_by,
            action="job_application_received",
            message=f"{current_user.username} applied for {job.title}.",
            link=recruiter_link,
            from_user=current_user,
            commit=False,
            priority="high",
            entity_type="job_application",
            entity_id=app.id,
        )
    db.session.commit()
    flash("Application submitted. You can track its status from My Applications.", "success")
    return redirect(url_for("hiring.job_detail", slug=job.slug))


@hiring_bp.get("/hiring/applications")
@login_required
def my_applications():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    query = JobApplication.query.filter_by(user_id=current_user.id).join(Job).join(Company)
    if status in APPLICATION_STATUSES:
        query = query.filter(JobApplication.status == status)
    applications = query.order_by(JobApplication.updated_at.desc()).paginate(page=page, per_page=12, error_out=False)
    return render_template(
        "hiring/applications.html",
        applications=applications,
        statuses=APPLICATION_STATUSES,
        current_status=status,
    )


@hiring_bp.get("/hiring/jobs/<int:job_id>/applications")
@login_required
def job_applications(job_id):
    job = Job.query.get_or_404(job_id)
    if not job.user_can_manage(current_user):
        abort(403)
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    query = JobApplication.query.filter_by(job_id=job.id).join(User)
    if status in APPLICATION_STATUSES:
        query = query.filter(JobApplication.status == status)
    applications = query.order_by(JobApplication.updated_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template(
        "hiring/manage_applications.html",
        job=job,
        applications=applications,
        statuses=APPLICATION_STATUSES,
        current_status=status,
    )


@hiring_bp.post("/hiring/applications/<int:application_id>/status")
@login_required
def update_application_status(application_id):
    application = JobApplication.query.get_or_404(application_id)
    job = application.job
    if not job.user_can_manage(current_user):
        abort(403)

    status = request.form.get("status", "").strip()
    if status not in APPLICATION_STATUSES or status == "withdrawn":
        flash("Choose a valid application status.", "error")
        return redirect(url_for("hiring.job_applications", job_id=job.id))

    response = request.form.get("recruiter_response", "").strip()[:1000]
    application.status = status
    application.recruiter_response = response
    application.status_changed_at = datetime.utcnow()
    application.reviewed_by_id = current_user.id
    message = f"Your application for {job.title} is now {status.replace('-', ' ')}."
    if response:
        message = f"{message} Recruiter note: {response[:180]}"
    create_notification(
        user=application.user,
        action="job_application_status",
        message=message,
        link=url_for("hiring.my_applications"),
        from_user=current_user,
        commit=False,
        priority="high",
        entity_type="job_application",
        entity_id=application.id,
    )
    db.session.commit()
    flash("Application status updated and the applicant was notified.", "success")
    return redirect(url_for("hiring.job_applications", job_id=job.id))


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

    q = User.query.filter(
        User.active.is_(True),
        User.is_verified.is_(True),
        User.open_to_work.is_(True),
    )
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
