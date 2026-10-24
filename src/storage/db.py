"""Relational metadata storage adhering to zero-secret persistence rules.

Implements SQLite schema from architecture spec §6 & §7:
Tables: sessions, jobs, documents, parents, parse_cache, usage_daily.
CRITICAL INVARIANT: Zero key/secret columns in any table.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.ingest.chunking.models import ParentChunk

DEFAULT_DB_PATH = Path("provenance_rag.db")


class DatabaseManager:
    """Manages SQLite tables, parent context lookups, and session usage tracking."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = str(db_path)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Sessions table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    tier TEXT NOT NULL DEFAULT 'tier_a',
                    pages_used INTEGER DEFAULT 0,
                    docs_count INTEGER DEFAULT 0,
                    chunks_embedded INTEGER DEFAULT 0,
                    rerank_calls INTEGER DEFAULT 0,
                    questions_owner_llm INTEGER DEFAULT 0,
                    questions_own_llm INTEGER DEFAULT 0,
                    owner_tokens_used INTEGER DEFAULT 0,
                    request_count INTEGER DEFAULT 0
                )
                """
            )

            # 2. Jobs table - NO KEY COLUMN EVER
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    doc_id TEXT,
                    parser_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    pages INTEGER DEFAULT 0,
                    chunks INTEGER DEFAULT 0,
                    quality_flags TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
                """
            )

            # 3. Documents table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    page_count INTEGER NOT NULL,
                    parser_used TEXT NOT NULL,
                    parser_version TEXT DEFAULT '1.0',
                    quality_flags TEXT,
                    chunking_version TEXT DEFAULT 'hybrid-v1',
                    embedding_version TEXT DEFAULT 'emb-v1',
                    ingested_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
                """
            )

            # 4. Parents table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS parents (
                    parent_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    breadcrumb TEXT NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    page_start INTEGER NOT NULL,
                    page_end INTEGER NOT NULL,
                    FOREIGN KEY (doc_id) REFERENCES documents (doc_id)
                )
                """
            )

            # 5. Parse cache table (session-scoped only)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS parse_cache (
                    session_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    parser TEXT NOT NULL,
                    parser_version TEXT NOT NULL,
                    raw_result_blob TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, content_hash, parser, parser_version)
                )
                """
            )

            # 6. Usage daily table (owner global caps and meters)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_daily (
                    date TEXT PRIMARY KEY,
                    chunks_embedded INTEGER DEFAULT 0,
                    rerank_calls INTEGER DEFAULT 0,
                    owner_llm_tokens INTEGER DEFAULT 0,
                    jobs INTEGER DEFAULT 0
                )
                """
            )

            conn.commit()

    def insert_parents(self, parents: list[ParentChunk], session_id: str) -> None:
        """Insert parent context chunks into SQL."""
        if not parents:
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for p in parents:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO parents (
                        parent_id, doc_id, session_id, breadcrumb, text, token_count, page_start, page_end
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p.parent_id,
                        p.doc_id,
                        session_id,
                        p.breadcrumb,
                        p.text,
                        p.token_count,
                        p.page_start,
                        p.page_end,
                    ),
                )
            conn.commit()

    def get_parent(self, parent_id: str, scope: str) -> dict[str, Any] | None:
        """Fetch parent chunk strictly filtered by parent_id AND scope (session or demo)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT parent_id, doc_id, session_id, breadcrumb, text, token_count, page_start, page_end
                FROM parents
                WHERE parent_id = ? AND (session_id = ? OR session_id = 'demo')
                """,
                (parent_id, scope),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def create_or_get_session(self, session_id: str, tier: str = "tier_a") -> dict[str, Any]:
        """Ensure a session record exists and return its state."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)

            now_iso = datetime.now(UTC).isoformat()
            cursor.execute(
                """
                INSERT INTO sessions (session_id, created_at, tier)
                VALUES (?, ?, ?)
                """,
                (session_id, now_iso, tier),
            )
            conn.commit()
            return {
                "session_id": session_id,
                "created_at": now_iso,
                "tier": tier,
                "chunks_embedded": 0,
                "rerank_calls": 0,
                "questions_owner_llm": 0,
            }

    def increment_session_usage(self, session_id: str, chunks_embedded: int = 0, rerank_calls: int = 0) -> None:
        """Increment session counters for owner spend protection."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET chunks_embedded = chunks_embedded + ?,
                    rerank_calls = rerank_calls + ?
                WHERE session_id = ?
                """,
                (chunks_embedded, rerank_calls, session_id),
            )
            conn.commit()
