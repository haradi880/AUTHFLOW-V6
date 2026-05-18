from datetime import datetime
from math import floor, pow

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import XPTransaction


XP_REWARDS = {
    "daily_login": 10,
    "publish_blog": 50,
    "receive_blog_like": 8,
    "publish_project": 60,
    "receive_project_star": 10,
    "comment": 12,
    "receive_follow": 15,
    "complete_profile": 100,
    "daily_devlog": 20,
}

DAILY_CAPPED_ACTIONS = {"daily_login", "daily_devlog"}


def xp_for_level(level):
    """Cumulative XP needed to reach a level. Level 1 starts at 0 XP."""
    level = max(1, int(level or 1))
    if level <= 1:
        return 0
    return floor(100 * pow(level - 1, 1.6))


def level_from_xp(total_xp):
    total_xp = max(0, int(total_xp or 0))
    level = 1
    while xp_for_level(level + 1) <= total_xp:
        level += 1
    return level


def xp_progress(total_xp):
    level = level_from_xp(total_xp)
    current_floor = xp_for_level(level)
    next_floor = xp_for_level(level + 1)
    current = max(0, int(total_xp or 0) - current_floor)
    needed = max(1, next_floor - current_floor)
    return {
        "level": level,
        "current": current,
        "needed": needed,
        "percent": min(100, round((current / needed) * 100)),
        "total": int(total_xp or 0),
        "next_level_total": next_floor,
    }


def _bucket_for(action, awarded_at):
    if action in DAILY_CAPPED_ACTIONS:
        return awarded_at.strftime("%Y-%m-%d")
    return None


def award_xp(user, action, source=None, points=None, meta=None, commit=True):
    """Award XP once for unique source actions and once per day for capped actions."""
    if not user or not getattr(user, "id", None):
        return None
    if action not in XP_REWARDS and points is None:
        raise ValueError(f"Unknown XP action: {action}")

    awarded_at = datetime.utcnow()
    points = int(points if points is not None else XP_REWARDS[action])
    source_type = source.__class__.__name__.lower() if source is not None else None
    source_id = getattr(source, "id", None) if source is not None else None
    transaction = XPTransaction(
        user_id=user.id,
        action=action,
        points=points,
        source_type=source_type,
        source_id=source_id,
        meta=meta or {},
        awarded_at=awarded_at,
        bucket_key=_bucket_for(action, awarded_at),
    )
    db.session.add(transaction)
    try:
        user.xp_total = (user.xp_total or 0) + points
        user.level = level_from_xp(user.xp_total)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return transaction
    except IntegrityError:
        db.session.rollback()
        return None


def maybe_award_profile_completion(user):
    if user.profile_completion() < 90 or user.profile_xp_awarded_at:
        return None
    transaction = award_xp(user, "complete_profile", source=user, commit=False)
    if transaction:
        user.profile_xp_awarded_at = datetime.utcnow()
        db.session.commit()
    return transaction
