import math
import time
from dataclasses import dataclass

import requests


DEFAULT_SMOKE_TARGETS = [
    {"path": "/healthz", "expected": {200}},
    {"path": "/readyz", "expected": {200}},
    {"path": "/blogs", "expected": {200}},
    {"path": "/projects", "expected": {200}},
    {"path": "/login", "expected": {200}},
    {"path": "/messages", "expected": {302}},
    {"path": "/dashboard/content", "expected": {302}},
]


@dataclass
class SmokeResult:
    path: str
    ok: bool
    expected: list
    statuses: list
    durations_ms: list
    p95_ms: float
    error: str = ""


def _p95(values):
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, max(0, math.ceil(len(sorted_values) * 0.95) - 1))
    return sorted_values[index]


def _request_internal(client, path):
    started = time.perf_counter()
    response = client.get(path, follow_redirects=False)
    return response.status_code, (time.perf_counter() - started) * 1000


def _request_external(base_url, path, timeout):
    started = time.perf_counter()
    response = requests.get(f"{base_url.rstrip('/')}{path}", allow_redirects=False, timeout=timeout)
    return response.status_code, (time.perf_counter() - started) * 1000


def run_smoke_targets(app=None, base_url=None, iterations=1, timeout=10, max_p95_ms=1000):
    if not app and not base_url:
        raise ValueError("Provide either a Flask app or base_url.")
    iterations = max(1, int(iterations or 1))
    results = []

    client = app.test_client() if app and not base_url else None
    for target in DEFAULT_SMOKE_TARGETS:
        statuses = []
        durations = []
        error = ""
        for _ in range(iterations):
            try:
                if base_url:
                    status, duration = _request_external(base_url, target["path"], timeout)
                else:
                    status, duration = _request_internal(client, target["path"])
                statuses.append(status)
                durations.append(round(duration, 2))
            except Exception as exc:
                error = f"{exc.__class__.__name__}: {exc}"
                break

        expected = set(target["expected"])
        p95 = round(_p95(durations), 2)
        ok = not error and statuses and all(status in expected for status in statuses) and p95 <= max_p95_ms
        results.append(
            SmokeResult(
                path=target["path"],
                ok=ok,
                expected=sorted(expected),
                statuses=statuses,
                durations_ms=durations,
                p95_ms=p95,
                error=error,
            )
        )
    return results


def smoke_summary(results):
    failures = sum(1 for result in results if not result.ok)
    return {"total": len(results), "failures": failures}
