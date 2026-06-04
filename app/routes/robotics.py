"""Robotics Hub blueprint: robotics projects, files, and specialized feed."""

import secrets
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import RoboticsFile, RoboticsProject, Tag
from app.services.content import generate_slug, sync_tags
from app.utils.rate_limit import rate_limit
from app.utils.uploads import _remove_local_after_cloud_upload, public_upload_url, scan_file_for_virus, upload_to_supabase
from app.utils.uploads_secure import delete_file_secure, save_upload_secure

robotics_bp = Blueprint("robotics", __name__)

PROJECT_TYPES = [
    ("robot", "Robot"),
    ("drone", "Drone"),
    ("iot", "IoT"),
    ("cnc", "CNC"),
    ("embedded", "Embedded"),
    ("ros", "ROS"),
    ("arduino", "Arduino"),
    ("esp32", "ESP32"),
    ("rpi", "Raspberry Pi"),
    ("3dprint", "3D Printing"),
    ("ai-robotics", "AI Robotics"),
    ("other", "Other"),
]

DIFFICULTY_LEVELS = ["beginner", "intermediate", "advanced", "expert"]
FILE_TYPES = ["cad", "stl", "bom", "schematic", "firmware", "code", "datasheet", "other"]
ALLOWED_ROBOTICS_FILE_EXTENSIONS = {
    "pdf", "txt", "md", "csv", "json", "zip",
    "ino", "py", "cpp", "c", "h", "hpp",
    "stl", "step", "stp", "obj", "dxf", "svg",
}


def _choice(value, allowed, default):
    return value if value in allowed else default


def _save_robotics_file(file):
    if not file or not file.filename or "." not in file.filename:
        return None, "Choose a file to upload."

    ext = file.filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_ROBOTICS_FILE_EXTENSIONS:
        return None, "Unsupported file type."

    max_bytes = int(current_app.config.get("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
    size = getattr(file, "content_length", None)
    stream = getattr(file, "stream", None)
    if not size and stream and hasattr(stream, "tell") and hasattr(stream, "seek"):
        try:
            current = stream.tell()
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(current)
        except Exception:
            size = None
    if size is not None and size > max_bytes:
        return None, f"File is too large. Maximum size is {max_bytes // (1024 * 1024)} MB."

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    upload_folder = (upload_root / "projects").resolve()
    if upload_root not in upload_folder.parents and upload_folder != upload_root:
        return None, "Invalid upload path."
    upload_folder.mkdir(parents=True, exist_ok=True)
    base_name = secure_filename(file.filename.rsplit(".", 1)[0]) or "robotics-file"
    filename = f"{secrets.token_hex(8)}_{base_name}.{ext}"
    path = upload_folder / filename
    uploaded = False
    try:
        file.save(path)
        scan_file_for_virus(path)
        uploaded = upload_to_supabase(path, "projects", filename, getattr(file, "mimetype", None))
        if not uploaded and not current_app.config.get("TESTING") and current_app.config.get("APP_ENV") == "production":
            raise RuntimeError("Supabase upload storage is not configured.")
        _remove_local_after_cloud_upload(path, uploaded)
        return filename, None
    except Exception as exc:
        current_app.logger.warning("Robotics file upload failed: %s", exc)
        if path.exists():
            path.unlink(missing_ok=True)
        return None, "File could not be saved."


@robotics_bp.get("/robotics")
def index():
    page = request.args.get("page", 1, type=int)
    ptype = request.args.get("type", "")
    difficulty = request.args.get("difficulty", "")
    sort = request.args.get("sort", "latest")
    query = request.args.get("q", "").strip()

    q = RoboticsProject.query.filter_by(status="published")
    if ptype:
        q = q.filter_by(project_type=ptype)
    if difficulty:
        q = q.filter_by(difficulty=difficulty)
    if query:
        q = q.filter(RoboticsProject.title.ilike(f"%{query}%"))

    if sort == "popular":
        q = q.order_by(RoboticsProject.stars_count.desc())
    elif sort == "views":
        q = q.order_by(RoboticsProject.views_count.desc())
    else:
        q = q.order_by(RoboticsProject.created_at.desc())

    projects = q.paginate(page=page, per_page=12, error_out=False)

    return render_template(
        "robotics/index.html",
        projects=projects,
        project_types=PROJECT_TYPES,
        difficulty_levels=DIFFICULTY_LEVELS,
        current_type=ptype,
        current_difficulty=difficulty,
        current_sort=sort,
        query=query,
    )


@robotics_bp.get("/robotics/<slug>")
def project_detail(slug):
    project = RoboticsProject.query.filter_by(slug=slug, status="published").first_or_404()
    project.views_count = (project.views_count or 0) + 1
    db.session.commit()
    return render_template("robotics/project_detail.html", project=project)


@robotics_bp.route("/robotics/upload", methods=["GET", "POST"])
@robotics_bp.route("/upload/robotics", methods=["GET", "POST"])
@login_required
@rate_limit(max_calls=10, window_seconds=600, scope="robotics-upload")
def upload_project():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        if len(title) < 3 or len(description) < 10:
            flash("Add a clear title and a useful description.", "error")
            return render_template("robotics/upload.html", project_types=PROJECT_TYPES, difficulty_levels=DIFFICULTY_LEVELS, file_types=FILE_TYPES)

        project = RoboticsProject(
            title=title,
            slug=generate_slug(title, RoboticsProject),
            description=description,
            project_type=_choice(request.form.get("project_type"), {item[0] for item in PROJECT_TYPES}, "other"),
            difficulty=_choice(request.form.get("difficulty"), set(DIFFICULTY_LEVELS), "intermediate"),
            status=_choice(request.form.get("status"), {"draft", "published"}, "draft"),
            github_url=request.form.get("github_url", "").strip(),
            demo_url=request.form.get("demo_url", "").strip(),
            video_url=request.form.get("video_url", "").strip(),
            hardware_specs=request.form.get("hardware_specs", "").strip(),
            bom_data=request.form.get("bom_data", "").strip(),
            user_id=current_user.id,
        )

        thumbnail = request.files.get("thumbnail")
        if thumbnail and thumbnail.filename:
            filename, error = save_upload_secure(thumbnail, "projects")
            if filename:
                project.thumbnail = filename
            else:
                flash(f"Thumbnail upload failed: {error}", "error")

        db.session.add(project)
        sync_tags(project, request.form.get("tags", ""))
        db.session.flush()

        file_type = _choice(request.form.get("file_type"), set(FILE_TYPES), "other")
        file_description = request.form.get("file_description", "").strip()[:300]
        for upload in request.files.getlist("files")[:8]:
            if not upload or not upload.filename:
                continue
            filename, error = _save_robotics_file(upload)
            if filename:
                db.session.add(RoboticsFile(
                    filename=filename,
                    original_name=secure_filename(upload.filename),
                    file_type=file_type,
                    description=file_description,
                    project=project,
                ))
            else:
                flash(f"{upload.filename}: {error}", "error")

        db.session.commit()
        flash("Robotics project saved.", "success")
        if project.status == "published":
            return redirect(url_for("robotics.project_detail", slug=project.slug))
        return redirect(url_for("robotics.index"))

    return render_template("robotics/upload.html", project_types=PROJECT_TYPES, difficulty_levels=DIFFICULTY_LEVELS, file_types=FILE_TYPES)


@robotics_bp.get("/robotics/files/<int:file_id>/download")
def download_file(file_id):
    file = db.get_or_404(RoboticsFile, file_id)
    can_view_draft = current_user.is_authenticated and (file.project.user_id == current_user.id or current_user.is_admin)
    if file.project.status != "published" and not can_view_draft:
        flash("This file is not available.", "error")
        return redirect(url_for("robotics.index"))
    file.download_count = (file.download_count or 0) + 1
    db.session.commit()
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    local_path = (upload_root / "projects" / file.filename).resolve()
    if upload_root in local_path.parents and local_path.exists() and local_path.is_file():
        return send_from_directory(
            upload_root / "projects",
            file.filename,
            as_attachment=True,
            download_name=file.original_name or file.filename,
        )
    cloud_url = public_upload_url("projects", file.filename)
    if cloud_url:
        return redirect(cloud_url)
    flash("This file is not available.", "error")
    return redirect(url_for("robotics.project_detail", slug=file.project.slug))


@robotics_bp.post("/robotics/<int:project_id>/delete")
@login_required
def delete_project(project_id):
    project = db.get_or_404(RoboticsProject, project_id)
    if project.user_id != current_user.id and not current_user.is_admin:
        flash("You can only delete your own robotics projects.", "error")
        return redirect(url_for("robotics.project_detail", slug=project.slug))

    delete_file_secure(project.thumbnail, "projects")
    for file in project.files.all():
        delete_file_secure(file.filename, "projects")
    db.session.delete(project)
    db.session.commit()
    flash("Robotics project deleted.", "success")
    return redirect(url_for("robotics.index"))
