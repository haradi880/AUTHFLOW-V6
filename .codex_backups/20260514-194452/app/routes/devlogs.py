"""DevLog routes: build logs, live engagement, and the developer activity feed."""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models import (
    Blog,
    DevLog,
    DevLogBookmark,
    DevLogComment,
    DevLogLike,
    DevLogMedia,
    DevLogRepost,
    Project,
    Tag,
    User,
)
from app.services.devlogs import devlog_query, sync_devlog_tags, viewer_state_for
from app.services.gamification import award_xp
from app.services.notifications import create_notification
from app.utils.helpers import paginate
from app.utils.rate_limit import rate_limit
from app.utils.uploads import delete_file, save_media_upload


devlog_bp = Blueprint("devlogs", __name__)


def _wants_json():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json"


def _feed_context(page=1, sort="latest", tag_slug=None):
    author_ids = None
    if sort == "following":
        if current_user.is_authenticated:
            author_ids = [follow.followed_id for follow in current_user.followed.limit(500).all()]
        else:
            author_ids = []
        sort = "latest"

    query = devlog_query(sort=sort, author_ids=author_ids)
    if tag_slug:
        query = query.filter(DevLog.tags.any(Tag.slug == tag_slug))
    query = query.options(
        joinedload(DevLog.author),
        selectinload(DevLog.tags),
        selectinload(DevLog.media),
    )
    pagination = paginate(query, page, per_page=8)
    devlogs = pagination.items
    return pagination, devlogs, viewer_state_for(devlogs, current_user)


def _render_card(devlog, viewer_state=None):
    return render_template(
        "devlogs/_card.html",
        devlog=devlog,
        state=(viewer_state or {}).get(devlog.id, {}),
    )


@devlog_bp.get("/devfeed")
@devlog_bp.get("/devlogs")
def index():
    sort = request.args.get("sort", "latest")
    if sort not in {"latest", "trending", "following", "milestones"}:
        sort = "latest"
    page = request.args.get("page", 1, type=int)
    tag_slug = request.args.get("tag", "").strip() or None
    pagination, devlogs, viewer_state = _feed_context(page=page, sort=sort, tag_slug=tag_slug)

    if request.args.get("ajax"):
        return jsonify({
            "html": "".join(_render_card(devlog, viewer_state) for devlog in devlogs),
            "has_next": pagination.has_next,
            "next_page": pagination.next_num if pagination.has_next else None,
        })

    trending_tags = (
        Tag.query.join(Tag.devlogs)
        .group_by(Tag.id)
        .order_by(db.func.count(DevLog.id).desc(), Tag.name.asc())
        .limit(12)
        .all()
    )
    top_creators = User.query.filter_by(active=True).order_by(User.xp_total.desc(), User.created_at.desc()).limit(6).all()
    top_projects = Project.query.filter_by(status="published").order_by(Project.stars_count.desc(), Project.created_at.desc()).limit(4).all()
    top_blogs = Blog.query.filter_by(status="published").order_by(Blog.likes_count.desc(), Blog.created_at.desc()).limit(4).all()

    return render_template(
        "devlogs/index.html",
        devlogs=devlogs,
        pagination=pagination,
        viewer_state=viewer_state,
        sort=sort,
        trending_tags=trending_tags,
        top_creators=top_creators,
        top_projects=top_projects,
        top_blogs=top_blogs,
    )


@devlog_bp.post("/devlogs")
@login_required
@rate_limit(max_calls=12, window_seconds=300, scope="devlogs")
def create():
    content = request.form.get("content", "").strip()
    if len(content) < 3:
        message = "DevLog must include at least 3 characters."
        if _wants_json():
            return jsonify({"error": message}), 400
        flash(message, "error")
        return redirect(url_for("devlogs.index"))

    progress = request.form.get("progress", 0, type=int)
    progress = max(0, min(100, progress or 0))
    milestone = request.form.get("milestone", "").strip()[:160]
    devlog = DevLog(
        content=content[:1200],
        progress=progress,
        milestone=milestone,
        user_id=current_user.id,
    )
    sync_devlog_tags(devlog, content, request.form.get("hashtags", ""))
    db.session.add(devlog)
    db.session.flush()

    for index, file in enumerate(request.files.getlist("media")[:4]):
        if not file or not file.filename:
            continue
        filename, media_type = save_media_upload(file, "devlogs")
        if filename:
            db.session.add(DevLogMedia(filename=filename, media_type=media_type, order=index, devlog=devlog))

    db.session.commit()
    award_xp(current_user, "daily_devlog")

    if _wants_json():
        viewer_state = viewer_state_for([devlog], current_user)
        return jsonify({"status": "created", "html": _render_card(devlog, viewer_state), "id": devlog.id}), 201

    flash("DevLog posted.", "success")
    return redirect(url_for("devlogs.index"))


@devlog_bp.get("/devlogs/<int:devlog_id>")
def detail(devlog_id):
    devlog = (
        DevLog.query.options(joinedload(DevLog.author), selectinload(DevLog.tags), selectinload(DevLog.media))
        .filter_by(id=devlog_id, visibility="public")
        .first_or_404()
    )
    comments = DevLogComment.query.filter_by(devlog_id=devlog.id).order_by(DevLogComment.created_at.asc()).all()
    viewer_state = viewer_state_for([devlog], current_user)
    return render_template("devlogs/detail.html", devlog=devlog, comments=comments, viewer_state=viewer_state)


@devlog_bp.post("/devlogs/<int:devlog_id>/like")
@login_required
def like(devlog_id):
    devlog = DevLog.query.get_or_404(devlog_id)
    existing = DevLogLike.query.filter_by(user_id=current_user.id, devlog_id=devlog.id).first()
    if existing:
        db.session.delete(existing)
        devlog.likes_count = max(0, devlog.likes_count - 1)
        db.session.commit()
        return jsonify({"status": "unliked", "count": devlog.likes_count})

    like_row = DevLogLike(user_id=current_user.id, devlog_id=devlog.id)
    db.session.add(like_row)
    devlog.likes_count += 1
    db.session.commit()
    if devlog.user_id != current_user.id:
        create_notification(
            user=devlog.author,
            action="like",
            message=f"{current_user.username} liked your DevLog",
            link=url_for("devlogs.detail", devlog_id=devlog.id),
            from_user=current_user,
        )
    return jsonify({"status": "liked", "count": devlog.likes_count})


@devlog_bp.post("/devlogs/<int:devlog_id>/bookmark")
@login_required
def bookmark(devlog_id):
    devlog = DevLog.query.get_or_404(devlog_id)
    existing = DevLogBookmark.query.filter_by(user_id=current_user.id, devlog_id=devlog.id).first()
    if existing:
        db.session.delete(existing)
        devlog.bookmarks_count = max(0, devlog.bookmarks_count - 1)
        db.session.commit()
        return jsonify({"status": "unbookmarked", "count": devlog.bookmarks_count})

    db.session.add(DevLogBookmark(user_id=current_user.id, devlog_id=devlog.id))
    devlog.bookmarks_count += 1
    db.session.commit()
    return jsonify({"status": "bookmarked", "count": devlog.bookmarks_count})


@devlog_bp.post("/devlogs/<int:devlog_id>/repost")
@login_required
def repost(devlog_id):
    devlog = DevLog.query.get_or_404(devlog_id)
    if devlog.user_id == current_user.id:
        return jsonify({"error": "You cannot repost your own DevLog."}), 400

    existing = DevLogRepost.query.filter_by(user_id=current_user.id, devlog_id=devlog.id).first()
    if existing:
        db.session.delete(existing)
        devlog.reposts_count = max(0, devlog.reposts_count - 1)
        db.session.commit()
        return jsonify({"status": "unreposted", "count": devlog.reposts_count})

    db.session.add(DevLogRepost(user_id=current_user.id, devlog_id=devlog.id))
    devlog.reposts_count += 1
    db.session.commit()
    create_notification(
        user=devlog.author,
        action="repost",
        message=f"{current_user.username} reposted your DevLog",
        link=url_for("devlogs.detail", devlog_id=devlog.id),
        from_user=current_user,
    )
    return jsonify({"status": "reposted", "count": devlog.reposts_count})


@devlog_bp.post("/devlogs/<int:devlog_id>/comments")
@login_required
@rate_limit(max_calls=20, window_seconds=300, scope="devlog-comments")
def comment(devlog_id):
    devlog = DevLog.query.get_or_404(devlog_id)
    content = request.form.get("content", "").strip()
    if not content:
        return jsonify({"error": "Comment cannot be empty."}), 400

    comment_row = DevLogComment(content=content[:600], user_id=current_user.id, devlog_id=devlog.id)
    db.session.add(comment_row)
    devlog.comments_count += 1
    db.session.commit()
    award_xp(current_user, "comment", source=comment_row)

    if devlog.user_id != current_user.id:
        create_notification(
            user=devlog.author,
            action="comment",
            message=f"{current_user.username} commented on your DevLog",
            link=url_for("devlogs.detail", devlog_id=devlog.id),
            from_user=current_user,
        )

    html = render_template("devlogs/_comment.html", comment=comment_row)
    return jsonify({"status": "created", "html": html, "count": devlog.comments_count})


@devlog_bp.post("/devlogs/<int:devlog_id>/pin")
@login_required
def pin(devlog_id):
    devlog = DevLog.query.get_or_404(devlog_id)
    if devlog.user_id != current_user.id and not current_user.is_admin:
        return jsonify({"error": "You can only pin your own DevLogs."}), 403
    devlog.is_pinned = not devlog.is_pinned
    db.session.commit()
    return jsonify({"status": "pinned" if devlog.is_pinned else "unpinned", "is_pinned": devlog.is_pinned})


@devlog_bp.post("/devlogs/media/<int:media_id>/delete")
@login_required
def delete_media(media_id):
    media = DevLogMedia.query.get_or_404(media_id)
    if media.devlog.user_id != current_user.id and not current_user.is_admin:
        return jsonify({"error": "You can only remove media from your own DevLogs."}), 403
    delete_file(media.filename, "devlogs")
    db.session.delete(media)
    db.session.commit()
    return jsonify({"status": "deleted"})
