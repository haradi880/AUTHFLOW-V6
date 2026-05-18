"""
Soft Delete System - Enables content recovery and audit trails.
"""

import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy.orm import declarative_mixin, declared_attr
from flask import current_app

from app.extensions import db
from app.utils.audit import audit_log, AuditEventType


class DeletedContent(db.Model):
    """Archive for deleted content with recovery capability."""
    
    __tablename__ = "deleted_content_archive"
    
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(50), nullable=False, index=True)  # blog, project, comment, etc.
    content_id = db.Column(db.Integer, nullable=False, index=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    deleted_by_username = db.Column(db.String(50))
    content_data = db.Column(db.JSON, nullable=False)  # Full serialized content
    reason = db.Column(db.String(255))  # Deletion reason
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, index=True)  # When recovery is no longer possible (30 days default)
    recovered = db.Column(db.Boolean, default=False, nullable=False)
    recovered_at = db.Column(db.DateTime)
    recovered_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    
    deleted_by = db.relationship("User", foreign_keys=[deleted_by_id], backref=db.backref("deleted_content", lazy="dynamic"))
    recovered_by = db.relationship("User", foreign_keys=[recovered_by_id])
    
    def __repr__(self):
        return f"<DeletedContent {self.content_type}:{self.content_id} at {self.deleted_at}>"
    
    def can_recover(self) -> bool:
        """Check if content can still be recovered."""
        return not self.recovered and self.expires_at > datetime.utcnow()


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
            user = User.query.get(user_id)
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
        archive = DeletedContent.query.get_or_404(archive_id)
        
        if archive.recovered:
            raise ValueError("Content has already been recovered")
        
        if not archive.can_recover():
            raise ValueError("Recovery period has expired")
        
        # Recreate the object from archive
        # This is simplified - in production, you'd have model-specific restoration logic
        content_data = archive.content_data.copy()
        content_data.pop('id', None)  # Remove ID to create new instance
        
        # Log restoration
        actor_username = None
        if user_id:
            from app.models import User
            user = User.query.get(user_id)
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
        
        return content_data
    except Exception as e:
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
        current_app.logger.error(f"Archive cleanup failed: {e}")
        return 0
