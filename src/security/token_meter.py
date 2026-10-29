"""Owner-LLM token reservation: estimate → reserve → generate → commit actuals.

Uses the same multi-bucket ledger as parser credits. BYOK calls skip owner buckets.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status

from src.generation.llm import DEFAULT_OUTPUT_TOKENS, TokenUsage
from src.ingest.chunking.tokenizer import estimate_tokens
from src.security.config import OwnerConfig
from src.security.credit_config import VISITOR_ALLOWANCE, today_str, visitor_bucket_id
from src.security.ledger import Bucket, Ledger
from src.storage.db import DatabaseManager

logger = logging.getLogger("provenance_rag.security.token_meter")


def estimate_generation_reserve(prompt: str, max_output: int = DEFAULT_OUTPUT_TOKENS) -> int:
    """Worst-case tokens to reserve before an owner-funded LLM call."""
    return max(1, estimate_tokens(prompt) + max_output)


def estimate_rewrite_reserve(query: str, history: list[dict[str, str]] | None) -> int:
    """Worst-case tokens for a follow-up rewrite (short output)."""
    hist_text = ""
    for turn in (history or [])[-3:]:
        hist_text += str(turn.get("content") or "")
    return max(1, estimate_tokens(query) + estimate_tokens(hist_text) + 256)


async def reserve_owner_llm_tokens(
    ledger: Ledger,
    session_id: str,
    client_ip: str,
    estimated: int,
    cfg: OwnerConfig,
) -> list[Bucket]:
    """Atomically reserve visitor-daily and global-daily owner LLM token buckets."""
    vid = visitor_bucket_id(session_id, client_ip)
    today = today_str()
    buckets = [
        Bucket(f"day:owner_llm:{today}", estimated, cfg.daily_max_owner_llm_tokens),
        Bucket(
            f"u:{vid}:llm:{today}",
            estimated,
            int(VISITOR_ALLOWANCE["llm_tokens_day"]),
        ),
    ]
    ok, failed_key = await ledger.reserve(buckets)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "The demo has reached its owner-LLM token capacity "
                f"(bucket={failed_key}). Provide your own LLM key to continue, "
                "or try again tomorrow."
            ),
            headers={"Retry-After": "86400"},
        )
    return buckets


async def commit_owner_llm_tokens(
    ledger: Ledger,
    buckets: list[Bucket],
    usage: TokenUsage,
    db: DatabaseManager,
    cfg: OwnerConfig,
    session_id: str | None = None,
) -> int:
    """Commit actual prompt+completion tokens and record them for observability."""
    actual = max(1, usage.total_tokens)
    if buckets:
        await ledger.commit(buckets, actual)
    record_daily_llm_tokens(db, actual, cfg)
    if session_id:
        _increment_session_owner_tokens(db, session_id, actual)
    return actual


async def release_owner_llm_tokens(ledger: Ledger, buckets: list[Bucket]) -> None:
    """Roll back a reservation when the LLM call never completed."""
    if buckets:
        await ledger.release(buckets)


def record_daily_llm_tokens(db: DatabaseManager, tokens_used: int, cfg: OwnerConfig) -> None:
    """Increment usage_daily.owner_llm_tokens and emit 50/80% budget alerts.

    Hard enforcement happens at reserve time. This is the observability counter.
    """
    today = today_str()
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
    daily_max = cfg.daily_max_owner_llm_tokens
    pct = (current / daily_max) * 100 if daily_max > 0 else 100
    if pct >= 80:
        logger.warning(
            f"BUDGET ALERT 80%%: owner_llm_tokens at {current}/{daily_max} ({pct:.1f}%%)."
        )
    elif pct >= 50:
        logger.warning(
            f"BUDGET ALERT 50%%: owner_llm_tokens at {current}/{daily_max} ({pct:.1f}%%)."
        )


def _increment_session_owner_tokens(db: DatabaseManager, session_id: str, tokens_used: int) -> None:
    with db._get_connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET owner_tokens_used = owner_tokens_used + ?
            WHERE session_id = ?
            """,
            (tokens_used, session_id),
        )
        conn.commit()
