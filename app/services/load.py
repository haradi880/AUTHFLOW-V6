import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

from app.services.smoke import DEFAULT_SMOKE_TARGETS


@dataclass
class LoadResult:
    path: str
    ok: bool
    expected: list
    requests: int
    concurrency: int
    statuses: dict
    errors: list
    min_ms: float
    avg_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    duration_ms: float
    rps: float


def _percentile(values, percentile):
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, max(0, math.ceil(len(sorted_values) * percentile) - 1))
    return sorted_values[index]


def _request_internal(app, path):
    started = time.perf_counter()
    with app.test_client() as client:
        response = client.get(path, follow_redirects=False)
        status_code = response.status_code
    return status_code, (time.perf_counter() - started) * 1000


def _request_external(base_url, path, timeout):
    started = time.perf_counter()
    response = requests.get(f"{base_url.rstrip('/')}{path}", allow_redirects=False, timeout=timeout)
    return response.status_code, (time.perf_counter() - started) * 1000


def _summarize_target(path, expected, requests_count, concurrency, statuses, durations, errors, elapsed_ms, max_p95_ms):
    status_counts = {}
    for status in statuses:
        status_counts[str(status)] = status_counts.get(str(status), 0) + 1

    expected = set(expected)
    ok = (
        not errors
        and len(statuses) == requests_count
        and all(status in expected for status in statuses)
        and _percentile(durations, 0.95) <= max_p95_ms
    )
    avg = (sum(durations) / len(durations)) if durations else 0.0
    return LoadResult(
        path=path,
        ok=ok,
        expected=sorted(expected),
        requests=requests_count,
        concurrency=concurrency,
        statuses=status_counts,
        errors=errors[:5],
        min_ms=round(min(durations), 2) if durations else 0.0,
        avg_ms=round(avg, 2),
        p50_ms=round(_percentile(durations, 0.50), 2),
        p95_ms=round(_percentile(durations, 0.95), 2),
        max_ms=round(max(durations), 2) if durations else 0.0,
        duration_ms=round(elapsed_ms, 2),
        rps=round((len(statuses) / (elapsed_ms / 1000)), 2) if elapsed_ms > 0 else 0.0,
    )


def run_load_targets(app=None, base_url=None, requests_per_target=10, concurrency=4, timeout=10, max_p95_ms=1500, targets=None):
    if not app and not base_url:
        raise ValueError("Provide either a Flask app or base_url.")

    requests_per_target = max(1, int(requests_per_target or 1))
    concurrency = max(1, min(int(concurrency or 1), requests_per_target))
    targets = targets or DEFAULT_SMOKE_TARGETS
    results = []

    for target in targets:
        path = target["path"]
        statuses = []
        durations = []
        errors = []
        started = time.perf_counter()

        def perform_request():
            if base_url:
                return _request_external(base_url, path, timeout)
            return _request_internal(app, path)

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(perform_request) for _ in range(requests_per_target)]
            for future in as_completed(futures):
                try:
                    status, duration = future.result()
                    statuses.append(status)
                    durations.append(duration)
                except Exception as exc:
                    errors.append(f"{exc.__class__.__name__}: {exc}")

        elapsed_ms = (time.perf_counter() - started) * 1000
        results.append(
            _summarize_target(
                path,
                target["expected"],
                requests_per_target,
                concurrency,
                statuses,
                durations,
                errors,
                elapsed_ms,
                max_p95_ms,
            )
        )

    return results


def load_summary(results):
    failures = sum(1 for result in results if not result.ok)
    total_requests = sum(result.requests for result in results)
    completed_requests = sum(sum(result.statuses.values()) for result in results)
    total_duration_ms = sum(result.duration_ms for result in results)
    failed_requests = total_requests - completed_requests + sum(len(result.errors) for result in results)
    return {
        "total": len(results),
        "failures": failures,
        "total_requests": total_requests,
        "completed_requests": completed_requests,
        "failed_requests": failed_requests,
        "aggregate_rps": round((completed_requests / (total_duration_ms / 1000)), 2) if total_duration_ms > 0 else 0.0,
    }
