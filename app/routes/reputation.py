"""Reputation blueprint — leaderboards, badges, streaks."""

from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user, login_required

from app.extensions import db
from app.models import User, Badge, UserBadge, Streak, LeaderboardSnapshot

reputation_bp = Blueprint("reputation", __name__)


@reputation_bp.get("/reputation")
def index():
    top_users = User.query.filter(User.active.is_(True)).order_by(User.xp_total.desc()).limit(20).all()
    badges = Badge.query.order_by(Badge.tier.desc(), Badge.name).all()

    user_badges = []
    user_streak = None
    if current_user.is_authenticated:
        user_badges = [ub.badge for ub in UserBadge.query.filter_by(user_id=current_user.id).all()]
        user_streak = Streak.query.filter_by(user_id=current_user.id).first()

    return render_template(
        "reputation/index.html",
        top_users=top_users,
        badges=badges,
        user_badges=user_badges,
        user_streak=user_streak,
    )


@reputation_bp.get("/reputation/leaderboard")
def leaderboard():
    period = request.args.get("period", "alltime")
    page = request.args.get("page", 1, type=int)

    if period == "alltime":
        users = User.query.filter(User.active.is_(True)).order_by(User.xp_total.desc()).paginate(page=page, per_page=50, error_out=False)
    else:
        users = User.query.filter(User.active.is_(True)).order_by(User.xp_total.desc()).paginate(page=page, per_page=50, error_out=False)

    return render_template("reputation/leaderboard.html", users=users, period=period)


@reputation_bp.get("/api/reputation/heatmap/<username>")
def heatmap_data(username):
    """Return contribution data for heatmap visualization."""
    from app.models import Blog, Project, DevLog
    from datetime import datetime, timedelta
    from collections import defaultdict

    user = User.query.filter(User.username == username, User.active.is_(True)).first_or_404()
    end = datetime.utcnow().date()
    start = end - timedelta(days=365)

    data = defaultdict(int)

    # Count blogs
    for b in Blog.query.filter(Blog.user_id == user.id, Blog.published_at >= datetime.combine(start, datetime.min.time())).all():
        if b.published_at:
            data[b.published_at.strftime("%Y-%m-%d")] += 1

    # Count projects
    for p in Project.query.filter(Project.user_id == user.id, Project.created_at >= datetime.combine(start, datetime.min.time())).all():
        data[p.created_at.strftime("%Y-%m-%d")] += 1

    # Count devlogs
    for d in DevLog.query.filter(DevLog.user_id == user.id, DevLog.created_at >= datetime.combine(start, datetime.min.time())).all():
        data[d.created_at.strftime("%Y-%m-%d")] += 1

    return jsonify({"contributions": dict(data)})
