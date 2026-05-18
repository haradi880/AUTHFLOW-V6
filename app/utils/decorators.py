"""
Route Decorators - Helper functions that wrap route functions.
They add extra functionality like requiring login or admin status.
"""

from functools import wraps
from flask import redirect, url_for, flash, session, request
from flask_login import current_user


def login_required(f):
    """
    Decorator: Requires user to be logged in.
    If not logged in, redirects to login page.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator: Requires user to be an admin.
    If not admin, returns 403 Forbidden.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        if not current_user.is_admin:
            flash('You do not have permission to access this page.', 'error')
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated_function


def owner_required(model_class):
    """
    Decorator factory: Requires user to own the resource.
    Usage: @owner_required(Blog)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get the resource ID from URL parameters
            resource_id = kwargs.get('blog_id') or kwargs.get('project_id')
            if not resource_id:
                return "Resource not found", 404
            
            # Find the resource
            resource = model_class.query.get_or_404(resource_id)
            
            # Check ownership
            if resource.user_id != current_user.id:
                flash('You can only edit your own content.', 'error')
                return redirect(url_for('main.home'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
