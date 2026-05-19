"""Small RQ-backed task queue wrapper with safe synchronous fallback."""

from flask import current_app


def enqueue_task(func, *args, queue_name="default", **kwargs):
    """Queue a task in production, or run it inline when async queues are disabled.

    The fallback keeps local development and tests deterministic while allowing
    Docker/Redis deployments to process email, notification, cleanup, and report
    jobs out of band.
    """
    if not current_app.config.get("TASK_QUEUE_ASYNC"):
        return func(*args, **kwargs)

    try:
        from redis import Redis
        from rq import Queue

        redis = Redis.from_url(current_app.config["REDIS_URL"])
        queue = Queue(queue_name, connection=redis)
        return queue.enqueue(func, *args, **kwargs)
    except Exception as exc:
        current_app.logger.warning("Task queue unavailable; running %s inline: %s", getattr(func, "__name__", func), exc)
        return func(*args, **kwargs)
