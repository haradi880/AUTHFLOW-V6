from collections import defaultdict, deque
from functools import wraps
from time import monotonic

from flask import abort, current_app, request
from flask_login import current_user


_buckets = defaultdict(deque)


def _identity(scope):
    user_part = current_user.get_id() if current_user.is_authenticated else request.remote_addr
    return f"{scope}:{user_part}:{request.endpoint}"


def rate_limit(max_calls=10, window_seconds=60, scope="default"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_app.config.get("RATELIMIT_ENABLED", True):
                return func(*args, **kwargs)
            if request.method in {"GET", "HEAD", "OPTIONS"}:
                return func(*args, **kwargs)
            key = _identity(scope)
            now = monotonic()
            bucket = _buckets[key]
            while bucket and bucket[0] <= now - window_seconds:
                bucket.popleft()
            if len(bucket) >= max_calls:
                abort(429, description="Too many requests. Please slow down and try again.")
            bucket.append(now)
            return func(*args, **kwargs)

        return wrapper

    return decorator
