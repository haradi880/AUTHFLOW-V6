"""
Password Confirmation System - Protects sensitive operations.
"""

from functools import wraps
from flask import session, request, flash, redirect, url_for
from flask_login import current_user
from app.models import User


def password_required(f):
    """
    Decorator: Requires password confirmation for sensitive operations.
    Stores confirmation in session with timestamp.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if password was recently confirmed
        if not session.get("password_confirmed_at"):
            # Store the intended action for redirect after password confirmation
            session["confirm_password_next"] = request.url
            flash("Please confirm your password to perform this action.", "warning")
            return redirect(url_for("auth.confirm_password"))
        
        # Check if confirmation is still valid (within 15 minutes)
        from datetime import datetime, timedelta
        confirmed_at = session.get("password_confirmed_at")
        if isinstance(confirmed_at, str):
            confirmed_at = datetime.fromisoformat(confirmed_at)
        
        if datetime.utcnow() - confirmed_at > timedelta(minutes=15):
            session.pop("password_confirmed_at", None)
            flash("Password confirmation expired. Please confirm again.", "warning")
            session["confirm_password_next"] = request.url
            return redirect(url_for("auth.confirm_password"))
        
        return f(*args, **kwargs)
    
    return decorated_function


def confirm_password(password: str) -> bool:
    """Verify password for current user."""
    if not current_user.is_authenticated:
        return False
    return current_user.check_password(password)


def set_password_confirmed():
    """Mark password as confirmed in session."""
    from datetime import datetime
    session["password_confirmed_at"] = datetime.utcnow().isoformat()
    session.permanent = True


def clear_password_confirmation():
    """Clear password confirmation from session."""
    session.pop("password_confirmed_at", None)
    session.pop("confirm_password_next", None)
