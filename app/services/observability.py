import json
import re
import threading
import time
import uuid
from collections import defaultdict

from flask import g, request


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
_lock = threading.Lock()
_started_at = time.time()
_request_counts = defaultdict(int)
_request_duration_sum = defaultdict(float)
_error_counts = defaultdict(int)


def request_id_from_headers():
    incoming = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
    if incoming and REQUEST_ID_PATTERN.match(incoming):
        return incoming
    return uuid.uuid4().hex


def start_request_timer():
    g.request_id = request_id_from_headers()
    g.request_started_at = time.perf_counter()


def request_duration_seconds():
    started = getattr(g, "request_started_at", None)
    if started is None:
        return 0.0
    return max(0.0, time.perf_counter() - started)


def record_request(response):
    method = request.method
    status_class = f"{response.status_code // 100}xx"
    key = (method, status_class)
    duration = request_duration_seconds()
    with _lock:
        _request_counts[key] += 1
        _request_duration_sum[key] += duration
        if response.status_code >= 500:
            _error_counts[(method, str(response.status_code))] += 1
    return duration


def structured_log(logger, level, event, **fields):
    payload = {
        "event": event,
        "request_id": getattr(g, "request_id", None),
        "method": getattr(request, "method", None),
        "path": getattr(request, "path", None),
        **fields,
    }
    logger.log(level, json.dumps({key: value for key, value in payload.items() if value is not None}, default=str))


def metrics_text(app_name="haradibots"):
    lines = [
        "# HELP haradibots_app_info Static application info.",
        "# TYPE haradibots_app_info gauge",
        f'haradibots_app_info{{app="{app_name}"}} 1',
        "# HELP haradibots_process_uptime_seconds Process uptime in seconds.",
        "# TYPE haradibots_process_uptime_seconds gauge",
        f"haradibots_process_uptime_seconds {time.time() - _started_at:.6f}",
        "# HELP haradibots_requests_total Total HTTP requests by method and status class.",
        "# TYPE haradibots_requests_total counter",
    ]
    with _lock:
        request_counts = dict(_request_counts)
        duration_sums = dict(_request_duration_sum)
        error_counts = dict(_error_counts)

    for (method, status_class), count in sorted(request_counts.items()):
        lines.append(f'haradibots_requests_total{{method="{method}",status_class="{status_class}"}} {count}')

    lines.extend(
        [
            "# HELP haradibots_request_duration_seconds_sum Total request duration by method and status class.",
            "# TYPE haradibots_request_duration_seconds_sum counter",
        ]
    )
    for (method, status_class), total in sorted(duration_sums.items()):
        lines.append(
            f'haradibots_request_duration_seconds_sum{{method="{method}",status_class="{status_class}"}} {total:.6f}'
        )

    lines.extend(
        [
            "# HELP haradibots_errors_total Total HTTP 5xx errors by method and status.",
            "# TYPE haradibots_errors_total counter",
        ]
    )
    for (method, status), count in sorted(error_counts.items()):
        lines.append(f'haradibots_errors_total{{method="{method}",status="{status}"}} {count}')

    return "\n".join(lines) + "\n"
