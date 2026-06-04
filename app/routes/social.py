"""Social Routes - Follow, followers, following."""

from flask import Blueprint, render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required
from app.extensions import db
from app.models import User, Follow, Notification, Message, ConversationMember
from app.services.notifications import create_notification, mark_notifications_seen, serialize_notification
from app.services.gamification import award_xp
from app.utils.rate_limit import rate_limit

social_bp = Blueprint('social', __name__)

@social_bp.route('/notifications')
@login_required
def notifications():
    """View user notifications."""
    user_notifications = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).all()

    for notification in user_notifications:
        notification.mark_seen()
    db.session.commit()

    return render_template('social/notifications.html', notifications=user_notifications)

@social_bp.route('/notifications/clear', methods=['POST'])
@login_required
def clear_notifications():
    """Delete all notifications for current user."""
    Notification.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return {'status': 'cleared'}

@social_bp.route('/api/notifications/count')
@login_required
def get_notifications_count():
    """Returns unread notification count for global polling."""
    count = db.session.query(db.func.count(Notification.id)).filter_by(user_id=current_user.id, is_read=False).scalar()
    return {'count': count}

@social_bp.route('/api/pulse')
@login_required
def get_activity_pulse():
    """Returns lightweight unread counts for live badges."""
    latest = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
    notification_count = db.session.query(db.func.count(Notification.id)).filter(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).scalar_subquery()
    conversation_message_count = db.session.query(db.func.count(Message.id)).join(
        ConversationMember,
        Message.conversation_id == ConversationMember.conversation_id,
    ).filter(
        ConversationMember.user_id == current_user.id,
        ConversationMember.is_active.is_(True),
        Message.sender_id != current_user.id,
        db.or_(
            ConversationMember.last_read_message_id.is_(None),
            Message.id > ConversationMember.last_read_message_id,
        ),
    ).scalar_subquery()
    legacy_message_count = db.session.query(db.func.count(Message.id)).filter(
        Message.conversation_id.is_(None),
        Message.recipient_id == current_user.id,
        Message.is_read.is_(False),
    ).scalar_subquery()
    notifications_count, messages_count = db.session.query(notification_count, conversation_message_count + legacy_message_count).one()
    return {
        'notifications': notifications_count,
        'messages': messages_count,
        'latest_notifications': [serialize_notification(notification) for notification in latest],
    }

@social_bp.route('/api/notifications')
@login_required
def list_notifications():
    """Return notification history for realtime drawers and mobile clients."""
    page = request.args.get("page", 1, type=int)
    unread_only = request.args.get("unread") == "1"
    query = Notification.query.filter_by(user_id=current_user.id)
    if unread_only:
        query = query.filter_by(is_read=False)
    pagination = query.order_by(Notification.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    for notification in pagination.items:
        notification.mark_seen()
    db.session.commit()
    return {
        "items": [serialize_notification(notification) for notification in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total,
        "unread": db.session.query(db.func.count(Notification.id)).filter_by(user_id=current_user.id, is_read=False).scalar(),
    }

@social_bp.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_notifications_read():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids")
    count = mark_notifications_seen(current_user, ids, read=True)
    return {"status": "ok", "updated": count}

@social_bp.route('/<username>/followers')
def followers(username):
    user = User.query.filter_by(username=username).first_or_404()
    followers_list = Follow.query.filter_by(followed_id=user.id).all()
    follower_ids = [follow.follower_id for follow in followers_list]
    users = User.query.filter(User.id.in_(follower_ids)).all() if follower_ids else []
    users_by_id = {follower.id: follower for follower in users}
    follower_users = [users_by_id[user_id] for user_id in follower_ids if user_id in users_by_id]
    return render_template('social/followers.html', user=user, followers=follower_users)

@social_bp.route('/<username>/following')
def following(username):
    user = User.query.filter_by(username=username).first_or_404()
    following_list = Follow.query.filter_by(follower_id=user.id).all()
    following_ids = [follow.followed_id for follow in following_list]
    users = User.query.filter(User.id.in_(following_ids)).all() if following_ids else []
    users_by_id = {followed.id: followed for followed in users}
    following_users = [users_by_id[user_id] for user_id in following_ids if user_id in users_by_id]
    return render_template('social/following.html', user=user, following=following_users)

@social_bp.route('/follow/<username>', methods=['POST'])
@login_required
@rate_limit(max_calls=30, window_seconds=300, scope="follow")
def follow_user(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user.id == current_user.id:
        return {'error': 'Cannot follow yourself'}, 400
    if current_user.is_following(user):
        current_user.unfollow(user)
        db.session.commit()
        return {'status': 'unfollowed'}
    else:
        current_user.follow(user)
        db.session.commit()
        award_xp(user, "receive_follow", source=Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first())
        create_notification(user=user, action='follow', 
                          message=f'{current_user.username} started following you',
                          link=url_for('main.public_profile', username=current_user.username),
                          from_user=current_user)
        return {'status': 'followed'}
