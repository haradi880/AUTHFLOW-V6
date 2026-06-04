import hashlib
from functools import wraps

from flask import current_app, make_response, request
from flask_login import current_user


def _redis_client():
    """Return a shared Redis client for lightweight public response caching."""
    if not current_app.config.get("REDIS_URL"):
        return None
    client = current_app.extensions.get("redis_cache_client")
    if client is not None:
        return client

    try:
        from redis import Redis

        client = Redis.from_url(
            current_app.config["REDIS_URL"],
            socket_connect_timeout=1,
            socket_timeout=1,
            retry_on_timeout=False,
        )
        current_app.extensions["redis_cache_client"] = client
        return client
    except Exception as exc:
        current_app.logger.info("Redis cache unavailable: %s", exc)
        return None


def _public_cache_key(prefix):
    raw = f"{request.method}:{request.host}:{request.full_path}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"haradibots:public-page:{prefix}:{digest}"


def _can_cache_public_response():
    if request.method != "GET":
        return False
    if request.headers.get("Cookie"):
        return False
    if getattr(current_user, "is_authenticated", False):
        return False
    return True


def public_response_cache(prefix, seconds=None):
    """Cache anonymous public HTML responses in Redis for slow public feeds."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_app.config.get("PUBLIC_PAGE_CACHE_ENABLED", True) or not _can_cache_public_response():
                return view_func(*args, **kwargs)

            ttl = int(seconds or current_app.config.get("PUBLIC_PAGE_CACHE_SECONDS") or 0)
            if ttl <= 0:
                return view_func(*args, **kwargs)

            client = _redis_client()
            if client is None:
                return view_func(*args, **kwargs)

            key = _public_cache_key(prefix)
            try:
                cached_body = client.get(key)
                if cached_body is not None:
                    response = make_response(cached_body)
                    response.headers["X-HaradiBots-Cache"] = "HIT"
                    return response
            except Exception as exc:
                current_app.logger.info("Redis cache read failed: %s", exc)
                return view_func(*args, **kwargs)

            response = make_response(view_func(*args, **kwargs))
            if response.status_code == 200 and response.mimetype == "text/html" and "Set-Cookie" not in response.headers:
                try:
                    client.setex(key, ttl, response.get_data())
                    response.headers["X-HaradiBots-Cache"] = "MISS"
                except Exception as exc:
                    current_app.logger.info("Redis cache write failed: %s", exc)
            return response

        return wrapped

    return decorator
