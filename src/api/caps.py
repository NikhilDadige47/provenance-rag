"""Owner cost caps, per-IP rate limiting, global daily budgets, and kill switch.

Implements roadmap P5-T2 & P5-T3 & architecture §9.1:

Per-session caps (atomic SQLite updates):
  - owner-LLM questions  (~15, also enforced per IP per day)
  - own-LLM-key questions (~100 per session)
  - rerank calls          (~30 per session)
  - chunks embedded       (~1500 per session)

Per-IP rate limits:
  - N requests per rolling minute
  - Daily owner-funded question cap per IP (persisted; refresh/private tab cannot reset)
  - Daily upload cap per IP

Daily global caps (usage_daily table):
  - Chunks embedded, rerank calls, owner-LLM tokens, jobs

Kill switch:
  - KILL_SWITCH_DISABLE_OWNER_LLM  → forces BYOK or 503
  - KILL_SWITCH_DISABLE_UPLOADS    → blocks upload routes (Phase 6)

Budget alert hooks:
  - Warning logged at 50% and 80% of daily caps (extendable to email/webhook)

All cap checks raise HTTP 429 (Too Many Requests) with human-readable messages.
"""

import hashlib
import logging
import threading
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status

from src.security.config import OwnerConfig, dev_loopback_unlimited, is_loopback_ip
from src.security.credit_config import VISITOR_ALLOWANCE
from src.storage.db import DatabaseManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process per-IP rate limiter (no Redis required for single-process deploy)
# ---------------------------------------------------------------------------

_ip_lock = threading.Lock()

# ip -> deque of request timestamps (float epoch) within the rolling window
_ip_request_timestamps: dict[str, deque[float]] = defaultdict(deque)

# Rate limit: max requests per IP in RATE_WINDOW_SECONDS
RATE_WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 20  # 20 req/min per IP (generous for portfolio)
MAX_DAILY_QUESTIONS_PER_IP = int(VISITOR_ALLOWANCE["session_max_questions_owner_llm"])
MAX_DAILY_UPLOADS_PER_IP = int(VISITOR_ALLOWANCE["docs_day"])


def _current_date_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _current_epoch() -> float:
    return datetime.now(UTC).timestamp()


def _canonical_ip(client_ip: str) -> str:
    """Collapse loopback aliases so localhost and 127.0.0.1 share one budget."""
    ip = (client_ip or "").strip().strip("[]").lower()
    if ip.startswith("::ffff:"):
        ip = ip[7:]
    if ip.count(":") == 1 and "." in ip:
        ip = ip.split(":", 1)[0]
    if is_loopback_ip(ip):
        return "127.0.0.1"
    return ip


def _hash_ip(client_ip: str) -> str:
    """Store a digest, never the raw address."""
    return hashlib.sha256(f"provenance-ip-v1:{_canonical_ip(client_ip)}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# Per-IP rate check
# ---------------------------------------------------------------------------


def check_ip_rate_limit(client_ip: str, cfg: OwnerConfig | None = None) -> None:
    """Enforce per-IP rolling-window rate limit.

    Raises:
        HTTPException 429 if the IP exceeds MAX_REQUESTS_PER_WINDOW in the last minute.
    """
    if dev_loopback_unlimited(cfg, client_ip):
        return
    client_ip = _canonical_ip(client_ip) or client_ip
    now = _current_epoch()
    cutoff = now - RATE_WINDOW_SECONDS

    with _ip_lock:
        ts_queue = _ip_request_timestamps[client_ip]
        # Prune stale timestamps
        while ts_queue and ts_queue[0] < cutoff:
            ts_queue.popleft()

        if len(ts_queue) >= MAX_REQUESTS_PER_WINDOW:
            logger.warning(f"Per-IP rate limit hit: ip={client_ip} count={len(ts_queue)}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded: maximum {MAX_REQUESTS_PER_WINDOW} requests per minute "
                    "per IP address. Please slow down and try again shortly."
                ),
                headers={"Retry-After": "60"},
            )

        ts_queue.append(now)


def get_ip_daily_owner_questions(
    db: DatabaseManager, client_ip: str, cfg: OwnerConfig | None = None
) -> int:
    """Owner-funded questions already used by this IP today (0 if none)."""
    if dev_loopback_unlimited(cfg, client_ip):
        return 0
    today = _current_date_str()
    ip_hash = _hash_ip(client_ip)
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT owner_questions FROM ip_usage_daily WHERE ip_hash = ? AND date = ?",
            (ip_hash, today),
        ).fetchone()
    return int(row["owner_questions"] or 0) if row else 0


def check_and_increment_ip_owner_questions(
    db: DatabaseManager, client_ip: str, cfg: OwnerConfig
) -> int:
    """Atomically consume one owner-funded question for this IP today.

    Refresh and private tabs share this counter. BYOK chats must not call it.

    Raises:
        HTTPException 429 when today's owner-funded budget is gone.
    """
    if dev_loopback_unlimited(cfg, client_ip):
        return 0
    cap = cfg.session_max_questions_owner_llm
    today = _current_date_str()
    ip_hash = _hash_ip(client_ip)
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ip_usage_daily (ip_hash, date, owner_questions, uploads)
            VALUES (?, ?, 0, 0)
            ON CONFLICT(ip_hash, date) DO NOTHING
            """,
            (ip_hash, today),
        )
        # changes(), not cursor.rowcount. libsql/Turso's rowcount is a running
        # total for the connection, so INSERT + UPDATE reports 2 and a
        # `rowcount != 1` check rejects the visitor's first question.
        # RETURNING also leaves the statement open and commit then fails.
        cursor.execute(
            """
            UPDATE ip_usage_daily
            SET owner_questions = owner_questions + 1
            WHERE ip_hash = ? AND date = ? AND owner_questions < ?
            """,
            (ip_hash, today, cap),
        )
        changed = cursor.execute("SELECT changes()").fetchone()
        applied = int(changed[0] if changed is not None else 0)
        if applied != 1:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"You have used all {cap} owner-funded questions for today on this connection. "
                    "Provide your own LLM API key to continue, or try again tomorrow."
                ),
                headers={"Retry-After": "86400"},
            )
        cursor.execute(
            "SELECT owner_questions FROM ip_usage_daily WHERE ip_hash = ? AND date = ?",
            (ip_hash, today),
        )
        row = cursor.fetchone()
        conn.commit()
    return int(row["owner_questions"] or 1) if row else 1


def check_ip_daily_upload_limit(
    db: DatabaseManager, client_ip: str, cfg: OwnerConfig | None = None
) -> None:
    """Enforce per-IP daily upload cap before a job is accepted."""
    if dev_loopback_unlimited(cfg, client_ip):
        return
    today = _current_date_str()
    ip_hash = _hash_ip(client_ip)
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT uploads FROM ip_usage_daily WHERE ip_hash = ? AND date = ?",
            (ip_hash, today),
        ).fetchone()
    count = int(row["uploads"] or 0) if row else 0
    if count >= MAX_DAILY_UPLOADS_PER_IP:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You have reached the daily upload limit of {MAX_DAILY_UPLOADS_PER_IP} "
                "documents per IP address. Please try again tomorrow."
            ),
            headers={"Retry-After": "86400"},
        )


def increment_ip_daily_uploads(
    db: DatabaseManager, client_ip: str, cfg: OwnerConfig | None = None
) -> None:
    """Increment the IP's daily upload counter after a job is accepted."""
    if dev_loopback_unlimited(cfg, client_ip):
        return
    today = _current_date_str()
    ip_hash = _hash_ip(client_ip)
    with db._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ip_usage_daily (ip_hash, date, owner_questions, uploads)
            VALUES (?, ?, 0, 1)
            ON CONFLICT(ip_hash, date) DO UPDATE SET
                uploads = uploads + 1
            """,
            (ip_hash, today),
        )
        conn.commit()


def reset_ip_limiters() -> None:
    """Clear in-process IP rate-limit buckets. Used by tests only."""
    with _ip_lock:
        _ip_request_timestamps.clear()


# ---------------------------------------------------------------------------
# Kill switch checks
# ---------------------------------------------------------------------------


def check_kill_switch_owner_llm(cfg: OwnerConfig) -> None:
    """Raise 503 if the owner-LLM kill switch is active.

    Raises:
        HTTPException 503 if KILL_SWITCH_DISABLE_OWNER_LLM is True.
    """
    if cfg.kill_switch_disable_owner_llm:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The owner-funded LLM is temporarily disabled. "
                "Please provide your own LLM API key via the X-LLM-Key header to continue."
            ),
        )


def check_kill_switch_uploads(cfg: OwnerConfig) -> None:
    """Raise 503 if the upload kill switch is active.

    Raises:
        HTTPException 503 if KILL_SWITCH_DISABLE_UPLOADS is True.
    """
    if cfg.kill_switch_disable_uploads:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Document uploads are temporarily disabled for maintenance. "
                "The demo corpus is still available for chat."
            ),
        )


# ---------------------------------------------------------------------------
# Daily global cap checks  (usage_daily table)
# ---------------------------------------------------------------------------


def _get_or_create_daily_row(db: DatabaseManager, date_str: str) -> dict[str, Any]:
    """Fetch today's usage_daily row, creating it if absent."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usage_daily WHERE date = ?", (date_str,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        cursor.execute(
            """
            INSERT INTO usage_daily (date, chunks_embedded, rerank_calls, owner_llm_tokens, jobs)
            VALUES (?, 0, 0, 0, 0)
            """,
            (date_str,),
        )
        conn.commit()
        return {
            "date": date_str,
            "chunks_embedded": 0,
            "rerank_calls": 0,
            "owner_llm_tokens": 0,
            "jobs": 0,
        }


def _log_budget_alerts(metric: str, current: int, daily_max: int) -> None:
    """Emit structured warning logs at 50% and 80% of daily cap thresholds."""
    pct = (current / daily_max) * 100 if daily_max > 0 else 100
    if pct >= 80:
        logger.warning(
            f"BUDGET ALERT 80%%: {metric} at {current}/{daily_max} ({pct:.1f}%%). "
            "Consider enabling kill switch or raising provider budgets."
        )
    elif pct >= 50:
        logger.warning(f"BUDGET ALERT 50%%: {metric} at {current}/{daily_max} ({pct:.1f}%%).")


def check_and_increment_daily_chunks(
    db: DatabaseManager, new_chunks: int, cfg: OwnerConfig
) -> None:
    """Check and atomically increment the daily global chunk-embed counter.

    Raises:
        HTTPException 429 "Demo at capacity" if the daily cap is exceeded.
    """
    today = _current_date_str()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        # Atomic increment and fetch
        cursor.execute(
            """
            INSERT INTO usage_daily (date, chunks_embedded, rerank_calls, owner_llm_tokens, jobs)
            VALUES (?, ?, 0, 0, 0)
            ON CONFLICT(date) DO UPDATE SET chunks_embedded = chunks_embedded + ?
            """,
            (today, new_chunks, new_chunks),
        )
        cursor.execute("SELECT chunks_embedded FROM usage_daily WHERE date = ?", (today,))
        row = cursor.fetchone()
        conn.commit()

    current = row["chunks_embedded"] if row else new_chunks
    _log_budget_alerts("chunks_embedded", current, cfg.daily_max_chunks_embedded)

    if current > cfg.daily_max_chunks_embedded:
        _raise_demo_at_capacity("chunk embedding")


def check_and_increment_daily_rerank(db: DatabaseManager, cfg: OwnerConfig) -> None:
    """Check and atomically increment the daily global rerank call counter."""
    today = _current_date_str()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_daily (date, chunks_embedded, rerank_calls, owner_llm_tokens, jobs)
            VALUES (?, 0, 1, 0, 0)
            ON CONFLICT(date) DO UPDATE SET rerank_calls = rerank_calls + 1
            """,
            (today,),
        )
        cursor.execute("SELECT rerank_calls FROM usage_daily WHERE date = ?", (today,))
        row = cursor.fetchone()
        conn.commit()

    current = row["rerank_calls"] if row else 1
    _log_budget_alerts("rerank_calls", current, cfg.daily_max_rerank_calls)

    if current > cfg.daily_max_rerank_calls:
        _raise_demo_at_capacity("reranking")


def check_and_increment_daily_llm_tokens(
    db: DatabaseManager, tokens_used: int, cfg: OwnerConfig
) -> None:
    """Check and atomically increment the daily global owner-LLM token counter."""
    today = _current_date_str()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_daily (date, chunks_embedded, rerank_calls, owner_llm_tokens, jobs)
            VALUES (?, 0, 0, ?, 0)
            ON CONFLICT(date) DO UPDATE SET owner_llm_tokens = owner_llm_tokens + ?
            """,
            (today, tokens_used, tokens_used),
        )
        cursor.execute("SELECT owner_llm_tokens FROM usage_daily WHERE date = ?", (today,))
        row = cursor.fetchone()
        conn.commit()

    current = row["owner_llm_tokens"] if row else tokens_used
    _log_budget_alerts("owner_llm_tokens", current, cfg.daily_max_owner_llm_tokens)

    if current > cfg.daily_max_owner_llm_tokens:
        _raise_demo_at_capacity("owner LLM generation")


def check_and_increment_daily_jobs(db: DatabaseManager, cfg: OwnerConfig) -> None:
    """Atomically increment the daily global ingestion-job counter."""
    today = _current_date_str()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_daily (date, chunks_embedded, rerank_calls, owner_llm_tokens, jobs)
            VALUES (?, 0, 0, 0, 1)
            ON CONFLICT(date) DO UPDATE SET jobs = jobs + 1
            """,
            (today,),
        )
        cursor.execute("SELECT jobs FROM usage_daily WHERE date = ?", (today,))
        row = cursor.fetchone()
        conn.commit()

    current = row["jobs"] if row else 1
    _log_budget_alerts("jobs", current, cfg.daily_max_jobs)
    if current > cfg.daily_max_jobs:
        _raise_demo_at_capacity("document ingestion")


def _raise_demo_at_capacity(resource: str) -> None:
    """Raise a 429 'Demo at Capacity' error for global daily cap breaches."""
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"The demo has reached its daily {resource} capacity. "
            "The free demo resets at midnight UTC. "
            "Provide your own LLM key (X-LLM-Key header) to continue without limits, "
            "or try again tomorrow."
        ),
        headers={"Retry-After": "86400"},
    )


# ---------------------------------------------------------------------------
# Per-session cap checks
# ---------------------------------------------------------------------------


def check_and_increment_session_owner_llm(
    db: DatabaseManager,
    session_id: str,
    cfg: OwnerConfig,
) -> None:
    """Atomically increment and check the per-session owner-LLM question counter.

    Raises:
        HTTPException 429 if the session owner-LLM cap is reached.
    """
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE sessions
            SET questions_owner_llm = questions_owner_llm + 1
            WHERE session_id = ?
            """,
            (session_id,),
        )
        cursor.execute(
            "SELECT questions_owner_llm FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.commit()

    current = row["questions_owner_llm"] if row else 1

    if current > cfg.session_max_questions_owner_llm:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You have used all {cfg.session_max_questions_owner_llm} owner-funded questions "
                "for this connection today. Provide your own LLM API key (X-LLM-Key header) "
                "to continue, or try again tomorrow."
            ),
        )


def check_and_increment_session_byok_llm(
    db: DatabaseManager,
    session_id: str,
    cfg: OwnerConfig,
) -> None:
    """Atomically increment and check the per-session BYOK LLM question counter.

    Raises:
        HTTPException 429 if the session BYOK cap is reached.
    """
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE sessions
            SET questions_own_llm = questions_own_llm + 1
            WHERE session_id = ?
            """,
            (session_id,),
        )
        cursor.execute(
            "SELECT questions_own_llm FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.commit()

    current = row["questions_own_llm"] if row else 1

    if current > cfg.session_max_questions_own_llm:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You have used all {cfg.session_max_questions_own_llm} questions "
                "allowed for sessions with your own LLM key. Start a new session to continue."
            ),
        )


def check_and_increment_session_rerank(
    db: DatabaseManager,
    session_id: str,
    cfg: OwnerConfig,
) -> None:
    """Atomically increment and check the per-session rerank call counter."""
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE sessions
            SET rerank_calls = rerank_calls + 1
            WHERE session_id = ?
            """,
            (session_id,),
        )
        cursor.execute(
            "SELECT rerank_calls FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.commit()

    current = row["rerank_calls"] if row else 1

    if current > cfg.session_max_rerank_calls:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Session reranking cap reached ({cfg.session_max_rerank_calls} calls). "
                "Start a new session to continue."
            ),
        )


# ---------------------------------------------------------------------------
# Demo scope read-only guard
# ---------------------------------------------------------------------------


def assert_demo_scope_readonly(scope: str, action: str = "write") -> None:
    """Raise 403 if a visitor attempts to write to the demo scope.

    The demo corpus (scope="demo") is permanently read-only for visitors.
    Only the owner can ingest into it via the offline scripts.

    Raises:
        HTTPException 403 if scope == "demo" and action is not a read.
    """
    if scope == "demo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"The demo corpus is read-only. {action.capitalize()} operations are not permitted "
                "on the shared demo corpus. Upload your own document to get a private session scope."
            ),
        )


# ---------------------------------------------------------------------------
# FastAPI dependency: combined rate-limit + IP check
# ---------------------------------------------------------------------------


async def enforce_rate_limits(request: Request) -> None:
    """FastAPI dependency: enforce per-IP rate limit on every incoming request.

    Usage:
        @router.post("/chat", dependencies=[Depends(enforce_rate_limits)])
    """
    cfg = getattr(request.app.state, "cfg", None)
    check_ip_rate_limit(client_ip_from_request(request), cfg)


def client_ip_from_request(request: Request) -> str:
    """Stable client identity for daily caps.

    Development / Vite: use the TCP peer (the proxy), not X-Forwarded-For.
    The forwarded header is spoofable and splits ::1 vs 127.0.0.1 across
    localhost URLs, which reset the demo budget on refresh or a private tab.

    Production: trust the first X-Forwarded-For hop from the reverse proxy.
    """
    peer = request.client.host if request.client and request.client.host else ""
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    cfg = getattr(request.app.state, "cfg", None)
    env = (getattr(cfg, "app_env", None) or "development").lower()
    if env == "production":
        return _canonical_ip(forwarded or peer or "unknown") or "unknown"
    return _canonical_ip(peer or forwarded or "unknown") or "unknown"
