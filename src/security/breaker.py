"""Provider Circuit Breaker.

Implements §7.1 and §12 of token-engineering-guide.md:
- Reactive circuit breaker on 402 (quota exhausted): trips for 30 minutes (free to re-probe after TTL)
- Failure breaker on transient errors (429/5xx bursts): opens for 60 seconds after threshold failures
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

from src.storage.sql import open_sql_connection

logger = logging.getLogger("provenance_rag.security.breaker")


class Breaker:
    """Circuit breaker for external AI service providers."""

    def __init__(self, db_path: Path | str = "provenance_rag.db") -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_table()

    def _get_connection(self):
        return open_sql_connection(self.db_path, timeout=10.0, wal=False)

    def _init_table(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS circuit_breakers (
                    provider TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    opened_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    failure_count INTEGER DEFAULT 0,
                    first_failure_at REAL DEFAULT 0
                )
                """
            )
            conn.commit()

    async def is_open(self, provider: str) -> bool:
        """Check if circuit breaker is currently open (blocking calls)."""
        now = datetime.now(UTC).timestamp()

        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT expires_at, reason FROM circuit_breakers WHERE provider = ?", (provider,))
            row = cursor.fetchone()

            if not row:
                return False

            if now >= row["expires_at"]:
                # Expired -> auto-heal / half-open
                cursor.execute("DELETE FROM circuit_breakers WHERE provider = ?", (provider,))
                conn.commit()
                logger.info(f"Circuit breaker for '{provider}' expired (reason was '{row['reason']}'). Recovering lane.")
                return False

            return True

    async def trip_quota(self, provider: str, ttl_seconds: int = 1800) -> None:
        """Trip breaker on 402 (Quota/Payment exhausted).

        Defaults to 30 minutes (1800s). Re-probing after TTL is safe and free.
        """
        now = datetime.now(UTC).timestamp()
        expires = now + ttl_seconds

        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO circuit_breakers (provider, reason, opened_at, expires_at, failure_count)
                VALUES (?, 'quota_exhausted', ?, ?, 0)
                ON CONFLICT(provider) DO UPDATE SET
                    reason = 'quota_exhausted',
                    opened_at = excluded.opened_at,
                    expires_at = excluded.expires_at,
                    failure_count = 0
                """,
                (provider, now, expires),
            )
            conn.commit()

        logger.warning(
            f"Circuit breaker TRIPPED for provider '{provider}' due to 402 Quota Exhaustion. "
            f"Open for {ttl_seconds} seconds."
        )

    async def record_failure(
        self,
        provider: str,
        threshold: int = 5,
        window_seconds: int = 60,
        open_for_seconds: int = 60,
    ) -> None:
        """Track transient failures (5xx, rate limits) and trip breaker if threshold exceeded."""
        now = datetime.now(UTC).timestamp()

        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT failure_count, first_failure_at, expires_at FROM circuit_breakers WHERE provider = ?",
                (provider,),
            )
            row = cursor.fetchone()

            if not row or (now - row["first_failure_at"] > window_seconds and row["expires_at"] <= now):
                # New window
                cursor.execute(
                    """
                    INSERT INTO circuit_breakers (provider, reason, opened_at, expires_at, failure_count, first_failure_at)
                    VALUES (?, 'transient_monitoring', ?, 0, 1, ?)
                    ON CONFLICT(provider) DO UPDATE SET
                        reason = 'transient_monitoring',
                        opened_at = excluded.opened_at,
                        expires_at = 0,
                        failure_count = 1,
                        first_failure_at = excluded.first_failure_at
                    """,
                    (provider, now, now),
                )
            else:
                new_count = row["failure_count"] + 1
                if new_count >= threshold:
                    # Trip breaker
                    expires = now + open_for_seconds
                    cursor.execute(
                        """
                        UPDATE circuit_breakers
                        SET reason = 'transient_burst', opened_at = ?, expires_at = ?, failure_count = ?
                        WHERE provider = ?
                        """,
                        (now, expires, new_count, provider),
                    )
                    logger.warning(
                        f"Circuit breaker TRIPPED for '{provider}' after {new_count} transient failures. "
                        f"Open for {open_for_seconds}s."
                    )
                else:
                    cursor.execute(
                        "UPDATE circuit_breakers SET failure_count = ? WHERE provider = ?",
                        (new_count, provider),
                    )

            conn.commit()

    async def reset(self, provider: str) -> None:
        """Manually reset circuit breaker for a provider."""
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM circuit_breakers WHERE provider = ?", (provider,))
            conn.commit()
