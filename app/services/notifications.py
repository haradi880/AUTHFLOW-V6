from app.extensions import db
from app.models import Notification
from app.utils.email import send_email

def create_notification(user, action, message, link=None, from_user=None, commit=True, send_mail=True):
    notification = Notification(
        user_id=user.id,
        action=action,
        message=message,
        link=link,
        from_user_id=from_user.id if from_user else None,
    )
    db.session.add(notification)
    if commit:
        db.session.commit()
    
    # Send email notification
    preference_name = {
        "message": "email_on_messages",
        "comment": "email_on_comments",
        "follow": "email_on_follows",
        "like": "email_on_likes",
    }.get(action)
    allowed_by_preference = getattr(user, preference_name, True) if preference_name else True

    if send_mail and allowed_by_preference and user.email:
        try:
            send_email(
                subject=f"New Notification: {action.capitalize()}",
                recipient=user.email,
                template="notification",
                message=message,
                link=link
            )
        except Exception as e:
            print(f"Error triggering email: {e}")
            
    return notification
