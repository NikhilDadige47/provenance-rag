"""Privacy-safe in-process metrics for Phase 9 observability.

Records request counts, error classes, latency, and job outcomes.
Never stores question text, document text, or API keys.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any

from src.storage.db import DatabaseManager

_lock = threading.Lock()
_started_at = time.time()
_requests_total = 0
_errors_4xx = 0
_errors_5xx = 0
_latency_ms_sum = 0.0
_jobs_by_status: dict[str, int] = defaultdict(int)


def record_request(status_code: int, duration_ms: float) -> None:
    """Count one completed HTTP request. Path is intentionally not stored."""
    global _requests_total, _errors_4xx, _errors_5xx, _latency_ms_sum
    with _lock:
        _requests_total += 1
        _latency_ms_sum += max(0.0, duration_ms)
        if 400 <= status_code < 500:
            _errors_4xx += 1
        elif status_code >= 500:
            _errors_5xx += 1


def record_job_status(status: str) -> None:
    """Count a job reaching a terminal or notable stage (ready/failed/queued)."""
    with _lock:
        _jobs_by_status[status] += 1


def snapshot(db: DatabaseManager | None = None) -> dict[str, Any]:
    """Return a JSON-serialisable metrics snapshot with no content fields."""
    with _lock:
        requests = _requests_total
        errors_4xx = _errors_4xx
        errors_5xx = _errors_5xx
        latency_sum = _latency_ms_sum
        jobs = dict(_jobs_by_status)
    avg_latency = round(latency_sum / requests, 1) if requests else 0.0
    daily: dict[str, int] = {
        "chunks_embedded": 0,
        "rerank_calls": 0,
        "owner_llm_tokens": 0,
        "jobs": 0,
    }
    if db is not None:
        try:
            from datetime import UTC, datetime

            today = datetime.now(UTC).strftime("%Y-%m-%d")
            with db._get_connection() as conn:
                row = conn.execute(
                    "SELECT chunks_embedded, rerank_calls, owner_llm_tokens, jobs "
                    "FROM usage_daily WHERE date = ?",
                    (today,),
                ).fetchone()
            if row:
                daily = {
                    "chunks_embedded": int(row["chunks_embedded"] or 0),
                    "rerank_calls": int(row["rerank_calls"] or 0),
                    "owner_llm_tokens": int(row["owner_llm_tokens"] or 0),
                    "jobs": int(row["jobs"] or 0),
                }
        except Exception:
            pass
    return {
        "uptime_seconds": int(time.time() - _started_at),
        "requests": requests,
        "errors_4xx": errors_4xx,
        "errors_5xx": errors_5xx,
        "latency_ms_avg": avg_latency,
        "jobs": jobs,
        "daily_spend": daily,
    }
