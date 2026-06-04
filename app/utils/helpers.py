"""
Helper Functions - Utility functions used throughout the application.
"""

from datetime import datetime
from types import SimpleNamespace
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


def paginate_without_count(query, page, per_page=12):
    """Paginate read-only feeds without running a total COUNT query."""
    page = max(1, int(page or 1))
    per_page = max(1, int(per_page or 1))
    rows = query.limit(per_page + 1).offset((page - 1) * per_page).all()
    has_next = len(rows) > per_page
    items = rows[:per_page]
    return SimpleNamespace(
        items=items,
        page=page,
        per_page=per_page,
        has_next=has_next,
        next_num=page + 1 if has_next else None,
        has_prev=page > 1,
        prev_num=page - 1 if page > 1 else None,
    )


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
