import re

from app.extensions import db
from app.models import DevLog, DevLogBookmark, DevLogLike, DevLogRepost, Tag
from app.services.content import generate_slug


HASHTAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_][A-Za-z0-9_-]{1,38})")


def normalize_hashtag(name):
    return (name or "").strip().lstrip("#").lower().replace("_", "-")


def extract_hashtags(content, extra_tags=""):
    discovered = [normalize_hashtag(match) for match in HASHTAG_RE.findall(content or "")]
    entered = [normalize_hashtag(tag) for tag in (extra_tags or "").replace("#", "").split(",")]
    tags = []
    for tag in discovered + entered:
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:8]


def sync_devlog_tags(devlog, content, extra_tags=""):
    devlog.tags = []
    for name in extract_hashtags(content, extra_tags):
        tag = Tag.query.filter_by(name=name).first()
        if not tag:
            tag = Tag(name=name, slug=generate_slug(name, Tag))
            db.session.add(tag)
        devlog.tags.append(tag)


def devlog_query(sort="latest", author_ids=None):
    query = DevLog.query.filter_by(visibility="public")
    if author_ids is not None:
        query = query.filter(DevLog.user_id.in_(author_ids) if author_ids else False)
    if sort == "trending":
        score = (
            DevLog.likes_count * 3
            + DevLog.comments_count * 4
            + DevLog.reposts_count * 5
            + DevLog.bookmarks_count
            + DevLog.progress
        )
        return query.order_by(DevLog.is_pinned.desc(), score.desc(), DevLog.created_at.desc())
    if sort == "milestones":
        return query.filter(DevLog.milestone.isnot(None), DevLog.milestone != "").order_by(DevLog.created_at.desc())
    return query.order_by(DevLog.is_pinned.desc(), DevLog.created_at.desc())


def viewer_state_for(devlogs, user):
    if not user or not getattr(user, "is_authenticated", False):
        return {}
    ids = [devlog.id for devlog in devlogs]
    if not ids:
        return {}
    liked = {row.devlog_id for row in DevLogLike.query.filter(DevLogLike.user_id == user.id, DevLogLike.devlog_id.in_(ids)).all()}
    bookmarked = {row.devlog_id for row in DevLogBookmark.query.filter(DevLogBookmark.user_id == user.id, DevLogBookmark.devlog_id.in_(ids)).all()}
    reposted = {row.devlog_id for row in DevLogRepost.query.filter(DevLogRepost.user_id == user.id, DevLogRepost.devlog_id.in_(ids)).all()}
    return {
        devlog_id: {
            "liked": devlog_id in liked,
            "bookmarked": devlog_id in bookmarked,
            "reposted": devlog_id in reposted,
        }
        for devlog_id in ids
    }
