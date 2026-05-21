from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import Notification
from app.services.task_queue import enqueue_task
from app.realtime import emit_notification
from app.utils.email import send_email


EMAIL_PREFERENCE_BY_ACTION = {
    "message": "email_on_messages",
    "comment": "email_on_comments",
    "follow": "email_on_follows",
    "like": "email_on_likes",
    "job_application_submitted": None,
    "job_application_received": None,
    "job_application_status": None,
    "team_invitation": None,
    "collaboration_request": None,
    "collaboration_update": None,
}


def create_notification(
    user,
    action,
    message,
    link=None,
    from_user=None,
    commit=True,
    send_mail=True,
    priority="normal",
    entity_type=None,
    entity_id=None,
    email_subject=None,
):
    notification = Notification(
        user_id=user.id,
        action=action,
        message=message,
        link=link,
        from_user_id=from_user.id if from_user else None,
        priority=priority,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.session.add(notification)
    if commit:
        db.session.commit()
    else:
        db.session.flush()

    preference_name = EMAIL_PREFERENCE_BY_ACTION.get(action)
    allowed_by_preference = getattr(user, preference_name, True) if preference_name else True
    if current_app.config.get("MAIL_SUPPRESS_SEND"):
        notification.email_status = "skipped"
        if commit:
            db.session.commit()
        emit_notification(user.id, serialize_notification(notification))
        return notification

    if send_mail and allowed_by_preference and user.email:
        try:
            if commit:
                from app.tasks import deliver_notification_email

                notification.email_status = "queued"
                db.session.commit()
                enqueue_task(deliver_notification_email, notification.id, queue_name="notifications")
            else:
                send_email(
                    subject=email_subject or _subject_for(action),
                    recipient=user.email,
                    template="notification",
                    message=message,
                    link=link,
                )
                notification.email_status = "sent"
                notification.email_sent_at = datetime.utcnow()
        except Exception as e:
            notification.email_status = "failed"
            notification.retry_count = (notification.retry_count or 0) + 1
            notification.last_error = str(e)[:500]
            if commit:
                db.session.commit()
            current_app.logger.warning("Notification email failed for user_id=%s action=%s: %s", user.id, action, e)
    elif not send_mail:
        notification.email_status = "skipped"

    emit_notification(user.id, serialize_notification(notification))
    return notification


def mark_notifications_seen(user, notification_ids=None, read=False):
    query = Notification.query.filter_by(user_id=user.id)
    if notification_ids:
        query = query.filter(Notification.id.in_(notification_ids))
    notifications = query.all()
    for notification in notifications:
        notification.mark_read() if read else notification.mark_seen()
    db.session.commit()
    return len(notifications)


def serialize_notification(notification):
    return {
        "id": notification.id,
        "action": notification.action,
        "message": notification.message,
        "link": notification.link,
        "is_read": notification.is_read,
        "seen_at": notification.seen_at.isoformat() if notification.seen_at else None,
        "created_at": notification.created_at.isoformat() + "Z",
        "priority": notification.priority,
        "entity_type": notification.entity_type,
        "entity_id": notification.entity_id,
    }


def _subject_for(action):
    labels = {
        "job_application_submitted": "Your job application was submitted",
        "job_application_received": "New job application received",
        "job_application_status": "Your application status was updated",
        "team_invitation": "You were invited to a team",
        "collaboration_request": "New collaboration request",
        "collaboration_update": "Collaboration update",
    }
    return labels.get(action, "New notification")
