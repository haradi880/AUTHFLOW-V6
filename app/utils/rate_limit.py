from functools import wraps

from flask import current_app, request
from flask_login import current_user

from app.extensions import limiter


def _identity(scope):
    user_part = current_user.get_id() if current_user.is_authenticated else request.remote_addr
    return f"{scope}:{user_part}:{request.endpoint}"


def rate_limit(max_calls=10, window_seconds=60, scope="default", methods=None):
    limited_methods = {method.upper() for method in (methods or {"POST", "PUT", "PATCH", "DELETE"})}
    limit_value = f"{max_calls} per {window_seconds} seconds"

    def decorator(func):
        limited_func = limiter.limit(limit_value, key_func=lambda: _identity(scope))(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_app.config.get("RATELIMIT_ENABLED", True):
                return func(*args, **kwargs)
            if request.method.upper() not in limited_methods:
                return func(*args, **kwargs)
            return limited_func(*args, **kwargs)

        return wrapper

    return decorator
