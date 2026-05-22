from datetime import datetime
from math import floor, pow

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Badge, UserBadge, XPTransaction


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

DEFAULT_BADGES = [
    {"slug": "first-login", "name": "First Login", "description": "Started your AuthFlow journey.", "icon": "1", "tier": "bronze", "category": "account", "criteria_type": "xp", "criteria_value": 10, "xp_reward": 0},
    {"slug": "profile-ready", "name": "Profile Ready", "description": "Completed a useful creator profile.", "icon": "ID", "tier": "silver", "category": "account", "criteria_type": "action", "criteria_value": 1, "xp_reward": 0},
    {"slug": "writer", "name": "Writer", "description": "Published a blog post.", "icon": "W", "tier": "bronze", "category": "content", "criteria_type": "action", "criteria_value": 1, "xp_reward": 0},
    {"slug": "builder", "name": "Builder", "description": "Published a project.", "icon": "B", "tier": "bronze", "category": "content", "criteria_type": "action", "criteria_value": 1, "xp_reward": 0},
    {"slug": "devlogger", "name": "DevLogger", "description": "Shared a build progress update.", "icon": "D", "tier": "bronze", "category": "social", "criteria_type": "action", "criteria_value": 1, "xp_reward": 0},
    {"slug": "level-5", "name": "Level 5", "description": "Reached level 5.", "icon": "5", "tier": "silver", "category": "reputation", "criteria_type": "level", "criteria_value": 5, "xp_reward": 0},
]

ACTION_BADGES = {
    "daily_login": ["first-login"],
    "complete_profile": ["profile-ready"],
    "publish_blog": ["writer"],
    "publish_project": ["builder"],
    "daily_devlog": ["devlogger"],
}


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


def trust_level_from_reputation(points):
    points = int(points or 0)
    if points >= 1500:
        return 5
    if points >= 700:
        return 4
    if points >= 250:
        return 3
    if points >= 75:
        return 2
    return 1


def contributor_tier_from_reputation(points):
    points = int(points or 0)
    if points >= 1500:
        return "legend"
    if points >= 700:
        return "expert"
    if points >= 250:
        return "builder"
    if points >= 75:
        return "contributor"
    return "newcomer"


def ensure_default_badges():
    existing = {badge.slug for badge in Badge.query.filter(Badge.slug.in_([item["slug"] for item in DEFAULT_BADGES])).all()}
    for item in DEFAULT_BADGES:
        if item["slug"] not in existing:
            db.session.add(Badge(**item))


def _award_badge(user, slug):
    badge = Badge.query.filter_by(slug=slug).first()
    if not badge or UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first():
        return None
    user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
    db.session.add(user_badge)
    return user_badge


def sync_user_gamification(user, action=None):
    ensure_default_badges()
    user.reputation_points = max(0, int((user.xp_total or 0) * 0.6))
    user.trust_level = trust_level_from_reputation(user.reputation_points)
    user.contributor_tier = contributor_tier_from_reputation(user.reputation_points)
    for slug in ACTION_BADGES.get(action, []):
        _award_badge(user, slug)
    if (user.level or 1) >= 5:
        _award_badge(user, "level-5")


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
        sync_user_gamification(user, action)
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
