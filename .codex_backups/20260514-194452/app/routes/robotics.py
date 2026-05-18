"""Robotics Hub blueprint — robotics projects, files, specialized feed."""

from flask import Blueprint, render_template, request
from flask_login import current_user

from app.extensions import db
from app.models import RoboticsProject, Tag

robotics_bp = Blueprint("robotics", __name__)

PROJECT_TYPES = [
    ("robot", "🤖 Robot"),
    ("drone", "🚁 Drone"),
    ("iot", "📡 IoT"),
    ("cnc", "⚙️ CNC"),
    ("embedded", "🔌 Embedded"),
    ("ros", "🧭 ROS"),
    ("arduino", "💡 Arduino"),
    ("esp32", "📶 ESP32"),
    ("rpi", "🍓 Raspberry Pi"),
    ("3dprint", "🖨️ 3D Printing"),
    ("ai-robotics", "🧠 AI Robotics"),
    ("other", "📦 Other"),
]

DIFFICULTY_LEVELS = ["beginner", "intermediate", "advanced", "expert"]


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
