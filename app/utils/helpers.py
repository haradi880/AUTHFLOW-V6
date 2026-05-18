"""
Helper Functions - Utility functions used throughout the application.
"""

from datetime import datetime
from app.services.auth import generate_otp
from app.services.content import calculate_reading_time, generate_slug
from app.services.notifications import create_notification


def paginate(query, page, per_page=12):
    """
    Helper function to paginate any SQLAlchemy query.
    
    Args:
        query: SQLAlchemy query object
        page: Current page number
        per_page: Number of items per page
    
    Returns:
        Pagination object with items and metadata
    """
    return query.paginate(page=page, per_page=per_page, error_out=False)


def format_datetime(dt):
    """Format a datetime object to a readable string."""
    if not dt:
        return ''
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.days == 0:
        if diff.seconds < 60:
            return 'Just now'
        elif diff.seconds < 3600:
            minutes = diff.seconds // 60
            return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
        else:
            hours = diff.seconds // 3600
            return f'{hours} hour{"s" if hours != 1 else ""} ago'
    elif diff.days == 1:
        return 'Yesterday'
    elif diff.days < 7:
        return f'{diff.days} days ago'
    else:
        return dt.strftime('%b %d, %Y')
