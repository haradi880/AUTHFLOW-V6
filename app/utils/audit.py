"""
Audit Logging System - Tracks security events and sensitive operations.
Essential for compliance, forensics, and abuse detection.
"""

import logging
from datetime import datetime
from enum import Enum

from flask import request, session, current_app
from flask_login import current_user

from app.extensions import db


class AuditEventType(Enum):
    """Enumeration of all audit event types."""
    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGIN_ATTEMPT_LOCKED = "login_attempt_locked"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"  # nosec B105
    PASSWORD_RESET = "password_reset"  # nosec B105
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_DELETED = "account_deleted"
    SUPPORT_REQUEST_CREATED = "support_request_created"
    EMAIL_CHANGED = "email_changed"
    
    # Authorization events
    ADMIN_GRANT = "admin_grant"
    ADMIN_REVOKE = "admin_revoke"
    PERMISSION_DENIED = "permission_denied"
    
    # Content operations
    CONTENT_CREATED = "content_created"
    CONTENT_MODIFIED = "content_modified"
    CONTENT_DELETED = "content_deleted"
    CONTENT_RESTORED = "content_restored"
    
    # Moderation
    CONTENT_PUBLISHED = "content_published"
    CONTENT_UNPUBLISHED = "content_unpublished"
    USER_SUSPENDED = "user_suspended"
    USER_UNSUSPENDED = "user_unsuspended"
    REPORT_CREATED = "report_created"
    REPORT_RESOLVED = "report_resolved"
    
    # File operations
    FILE_UPLOADED = "file_uploaded"
    FILE_DELETED = "file_deleted"
    FILE_REJECTED = "file_rejected"
    
    # API operations
    API_TOKEN_GENERATED = "api_token_generated"  # nosec B105
    API_TOKEN_REVOKED = "api_token_revoked"  # nosec B105
    
    # Suspicious activity
    SUSPICIOUS_ACCESS = "suspicious_access"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    CSRF_VALIDATION_FAILED = "csrf_validation_failed"
    INVALID_INPUT = "invalid_input"


def get_client_ip():
    """Extract client IP address from request headers."""
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    if request.headers.get("X-Real-IP"):
        return request.headers.get("X-Real-IP")
    return request.remote_addr


def get_request_context():
    """Get current request context."""
    return {
        "ip_address": get_client_ip(),
        "user_agent": request.headers.get("User-Agent", ""),
        "request_path": request.path,
        "request_method": request.method,
    }


def audit_log(
    event_type: str,
    description: str = None,
    target_id: int = None,
    target_type: str = None,
    actor_id: int = None,
    actor_username: str = None,
    metadata: dict = None,
    error_message: str = None,
    status_code: int = None,
):
    """
    Create an audit log entry.
    
    Args:
        event_type: Type of event (use AuditEventType enum)
        description: Human-readable description
        target_id: ID of the affected resource
        target_type: Type of affected resource (blog, project, user, etc.)
        actor_id: ID of user performing action (defaults to current_user)
        actor_username: Username of actor (for deleted users)
        metadata: Additional context as dictionary
        error_message: Error description if applicable
        status_code: HTTP status code if applicable
    """
    try:
        # Get actor info
        if actor_id is None and current_user.is_authenticated:
            actor_id = current_user.id
            actor_username = current_user.username
        elif actor_username is None and actor_id is not None:
            from app.models import User
            user = db.session.get(User, actor_id)
            if user:
                actor_username = user.username
        
        # Get request context
        context = get_request_context()
        
        from app.models import AuditLog

        # Create log entry
        event_value = event_type.value if hasattr(event_type, "value") else str(event_type)
        log_entry = AuditLog(
            event_type=event_value,
            actor_id=actor_id,
            actor_username=actor_username or "system",
            target_id=target_id,
            target_type=target_type,
            description=description,
            ip_address=context["ip_address"],
            user_agent=context["user_agent"],
            request_path=context["request_path"],
            request_method=context["request_method"],
            status_code=status_code,
            error_message=error_message,
            extra_metadata=metadata or {},
        )
        
        db.session.add(log_entry)
        db.session.commit()
        
        # Also log to application logger
        level = "error" if error_message else "info"
        log_message = f"[AUDIT] {event_value}: {description or ''}"
        if actor_username:
            log_message += f" by {actor_username}"
        if error_message:
            log_message += f" - Error: {error_message}"
        
        logger = logging.getLogger("audit")
        getattr(logger, level)(log_message)
        
    except Exception as e:
        # Don't crash if audit logging fails
        current_app.logger.error(f"Audit log creation failed: {e}")


def audit_log_delete_recovery(resource_type: str, resource_id: int, recovery_data: dict):
    """Store recovery data for deleted content."""
    try:
        audit_log(
            event_type=AuditEventType.CONTENT_DELETED,
            description=f"Deleted {resource_type} (ID: {resource_id})",
            target_id=resource_id,
            target_type=resource_type,
            metadata={"recovery_data": recovery_data},
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log deletion recovery data: {e}")


# Configure audit logger
def configure_audit_logging(app):
    """Configure audit logging handlers."""
    if not app.debug:
        # File handler for audit logs
        audit_handler = logging.handlers.RotatingFileHandler(
            "logs/audit.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=10
        )
        audit_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        
        audit_logger = logging.getLogger("audit")
        audit_logger.addHandler(audit_handler)
        audit_logger.setLevel(logging.INFO)
