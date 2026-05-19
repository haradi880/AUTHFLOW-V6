"""Background task entrypoints.

Run with:
    rq worker -u redis://redis:6379/0 default notifications maintenance
"""

from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import Notification
from app.utils.email import send_email


def deliver_notification_email(notification_id):
    app = create_app()
    with app.app_context():
        notification = db.session.get(Notification, notification_id)
        if not notification or not notification.user or not notification.user.email:
            return False
        try:
            send_email(
                subject=_subject_for(notification.action),
                recipient=notification.user.email,
                template="notification",
                message=notification.message,
                link=notification.link,
            )
            notification.email_status = "sent"
            notification.email_sent_at = datetime.utcnow()
            notification.last_error = None
            db.session.commit()
            return True
        except Exception as exc:
            notification.retry_count = (notification.retry_count or 0) + 1
            notification.email_status = "failed"
            notification.last_error = str(exc)[:500]
            db.session.commit()
            app.logger.warning("Notification email delivery failed id=%s: %s", notification_id, exc)
            return False


def cleanup_old_security_events(days=180):
    app = create_app()
    with app.app_context():
        from datetime import timedelta
        from app.models import LoginEvent

        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = LoginEvent.query.filter(LoginEvent.created_at < cutoff).delete(synchronize_session=False)
        db.session.commit()
        return deleted


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
