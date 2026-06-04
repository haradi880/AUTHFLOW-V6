"""
Soft Delete System - Enables content recovery and audit trails.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from flask import current_app

from app.extensions import db
from app.models import Blog, DeletedContent, DevLog, Project
from app.utils.audit import audit_log, AuditEventType


RESTORABLE_MODELS = {
    "blog": Blog,
    "project": Project,
    "devlog": DevLog,
}


def serialize_model(obj) -> Dict[str, Any]:
    """Serialize a SQLAlchemy model to JSON-safe dictionary."""
    result = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        if isinstance(value, datetime):
            result[column.name] = value.isoformat()
        elif isinstance(value, bytes):
            result[column.name] = value.decode('utf-8', errors='ignore')
        else:
            result[column.name] = value
    return result


def _deserialize_value(column, value):
    if value is None:
        return None
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        python_type = None
    if python_type is datetime and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return value


def _restore_model(archive: DeletedContent):
    model = RESTORABLE_MODELS.get(archive.content_type)
    if model is None:
        return archive.content_data.copy()

    content_data = archive.content_data.copy()
    content_data.pop("id", None)
    allowed_columns = {column.name: column for column in model.__table__.columns if column.name != "id"}
    values = {
        name: _deserialize_value(column, content_data[name])
        for name, column in allowed_columns.items()
        if name in content_data
    }
    restored = model(**values)
    db.session.add(restored)
    return restored


def soft_delete(
    obj,
    content_type: str,
    user_id: int = None,
    reason: str = None,
    recovery_days: int = 30,
) -> bool:
    """
    Soft delete a model instance - archive data before deletion.
    
    Args:
        obj: SQLAlchemy model instance to delete
        content_type: Type of content (blog, project, comment, etc.)
        user_id: User performing the deletion
        reason: Reason for deletion
        recovery_days: Days to keep recovery data (default 30)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get deletion actor info
        actor_username = None
        if user_id:
            from app.models import User
            user = db.session.get(User, user_id)
            if user:
                actor_username = user.username
        
        # Serialize content before deletion
        content_data = serialize_model(obj)
        content_id = obj.id if hasattr(obj, 'id') else None
        
        # Create archive entry
        archive = DeletedContent(
            content_type=content_type,
            content_id=content_id,
            deleted_by_id=user_id,
            deleted_by_username=actor_username or "system",
            content_data=content_data,
            reason=reason,
            expires_at=datetime.utcnow() + timedelta(days=recovery_days),
        )
        
        db.session.add(archive)
        
        # Actually delete the object
        db.session.delete(obj)
        db.session.commit()
        
        # Log the deletion
        audit_log(
            event_type=AuditEventType.CONTENT_DELETED,
            description=f"Deleted {content_type} (ID: {content_id})",
            target_id=content_id,
            target_type=content_type,
            actor_id=user_id,
            actor_username=actor_username,
            metadata={"reason": reason},
        )
        
        return True
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Soft delete failed: {e}")
        return False


def restore_deleted_content(archive_id: int, user_id: int = None) -> Optional[Any]:
    """
    Restore previously deleted content from archive.
    
    Args:
        archive_id: ID of the DeletedContent archive entry
        user_id: User performing the restoration
    
    Returns:
        The restored object, or None if restoration failed
    """
    try:
        archive = db.get_or_404(DeletedContent, archive_id)
        
        if archive.recovered:
            raise ValueError("Content has already been recovered")
        
        if not archive.can_recover():
            raise ValueError("Recovery period has expired")
        
        restored = _restore_model(archive)
        
        # Log restoration
        actor_username = None
        if user_id:
            from app.models import User
            user = db.session.get(User, user_id)
            if user:
                actor_username = user.username
        
        audit_log(
            event_type=AuditEventType.CONTENT_RESTORED,
            description=f"Restored {archive.content_type} (previously ID: {archive.content_id})",
            target_id=archive.content_id,
            target_type=archive.content_type,
            actor_id=user_id,
            actor_username=actor_username,
        )
        
        # Mark as recovered
        archive.recovered = True
        archive.recovered_at = datetime.utcnow()
        archive.recovered_by_id = user_id
        db.session.commit()
        
        return restored
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Content restoration failed: {e}")
        return None


def cleanup_expired_archives():
    """Delete archive entries that have expired their recovery period."""
    try:
        expired = DeletedContent.query.filter(
            DeletedContent.expires_at < datetime.utcnow()
        ).delete()
        db.session.commit()
        current_app.logger.info(f"Cleaned up {expired} expired archive entries")
        return expired
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Archive cleanup failed: {e}")
        return 0
