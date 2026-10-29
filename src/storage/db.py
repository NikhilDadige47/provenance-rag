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
        conn = sqlite3.connect(self.db_path, timeout=30)
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
                    filename TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
                """
            )
            cursor.execute("PRAGMA table_info(documents)")
            document_columns = {row[1] for row in cursor.fetchall()}
            if "filename" not in document_columns:
                cursor.execute("ALTER TABLE documents ADD COLUMN filename TEXT")

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

    def increment_session_usage(
        self, session_id: str, chunks_embedded: int = 0, rerank_calls: int = 0
    ) -> None:
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

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Fetch full session row by ID. Returns None if not found."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_daily_usage(self, date_str: str) -> dict[str, Any]:
        """Fetch the usage_daily row for a given date string (YYYY-MM-DD).

        Returns a zero-filled dict if no row exists yet.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usage_daily WHERE date = ?", (date_str,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return {
            "date": date_str,
            "chunks_embedded": 0,
            "rerank_calls": 0,
            "owner_llm_tokens": 0,
            "jobs": 0,
        }

    def list_expired_sessions(self, now_iso: str) -> list[str]:
        """Return session IDs whose expires_at is non-null and in the past."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id FROM sessions
                WHERE expires_at IS NOT NULL AND expires_at < ?
                """,
                (now_iso,),
            )
            return [row["session_id"] for row in cursor.fetchall()]

    def create_job(
        self,
        job_id: str,
        session_id: str,
        parser_name: str,
        doc_id: str | None = None,
        status: str = "queued",
    ) -> dict[str, Any]:
        """Create a new job record."""
        now_iso = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO jobs (job_id, session_id, doc_id, parser_name, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, session_id, doc_id, parser_name, status, now_iso),
            )
            conn.commit()
        return {
            "job_id": job_id,
            "session_id": session_id,
            "doc_id": doc_id,
            "parser_name": parser_name,
            "status": status,
            "started_at": now_iso,
        }

    def update_job(
        self,
        job_id: str,
        status: str,
        error_message: str | None = None,
        pages: int = 0,
        chunks: int = 0,
        quality_flags: str | None = None,
        doc_id: str | None = None,
    ) -> None:
        """Update job status and results."""
        finished_at = datetime.now(UTC).isoformat() if status in ("ready", "failed") else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if doc_id:
                cursor.execute(
                    """
                    UPDATE jobs
                    SET status = ?, error_message = ?, pages = ?, chunks = ?, quality_flags = ?, finished_at = ?, doc_id = ?
                    WHERE job_id = ?
                    """,
                    (
                        status,
                        error_message,
                        pages,
                        chunks,
                        quality_flags,
                        finished_at,
                        doc_id,
                        job_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE jobs
                    SET status = ?, error_message = ?, pages = ?, chunks = ?, quality_flags = ?, finished_at = ?
                    WHERE job_id = ?
                    """,
                    (status, error_message, pages, chunks, quality_flags, finished_at, job_id),
                )
            conn.commit()

    def get_job(self, job_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        """Fetch job by ID, optionally verifying session ownership."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute(
                    "SELECT * FROM jobs WHERE job_id = ? AND session_id = ?",
                    (job_id, session_id),
                )
            else:
                cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def insert_document(
        self,
        doc_id: str,
        session_id: str,
        title: str,
        content_hash: str,
        page_count: int,
        parser_used: str,
        parser_version: str = "1.0",
        quality_flags: str | None = None,
        chunking_version: str = "hybrid-v1",
        embedding_version: str = "emb-v1",
        filename: str | None = None,
    ) -> None:
        """Insert metadata for an ingested document."""
        now_iso = datetime.now(UTC).isoformat()
        original_name = filename or title
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO documents (
                    doc_id, session_id, title, content_hash, page_count,
                    parser_used, parser_version, quality_flags,
                    chunking_version, embedding_version, ingested_at, filename
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    session_id,
                    title,
                    content_hash,
                    page_count,
                    parser_used,
                    parser_version,
                    quality_flags,
                    chunking_version,
                    embedding_version,
                    now_iso,
                    original_name,
                ),
            )
            conn.commit()

    def list_documents(self, session_id: str) -> list[dict[str, Any]]:
        """List all documents belonging to a session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT d.*, COALESCE((
                    SELECT j.chunks FROM jobs j
                    WHERE j.doc_id = d.doc_id
                      AND j.session_id = d.session_id
                      AND j.status = 'ready'
                    ORDER BY j.finished_at DESC
                    LIMIT 1
                ), 0) AS chunk_count
                FROM documents d
                WHERE d.session_id = ?
                ORDER BY d.ingested_at DESC
                """,
                (session_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_document(self, doc_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        """Fetch document metadata by doc_id and optional session_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute(
                    "SELECT * FROM documents WHERE doc_id = ? AND session_id = ?",
                    (doc_id, session_id),
                )
            else:
                cursor.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_document(self, doc_id: str, session_id: str) -> None:
        """Delete document and its parent records from SQL."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM parents WHERE doc_id = ? AND session_id = ?",
                (doc_id, session_id),
            )
            cursor.execute(
                "DELETE FROM documents WHERE doc_id = ? AND session_id = ?",
                (doc_id, session_id),
            )
            cursor.execute(
                """
                UPDATE sessions
                SET docs_count = MAX(0, docs_count - 1)
                WHERE session_id = ?
                """,
                (session_id,),
            )
            conn.commit()

    def get_parse_cache(
        self, session_id: str, content_hash: str, parser: str, parser_version: str
    ) -> str | None:
        """Retrieve raw parsed StructuredDoc JSON from session cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT raw_result_blob FROM parse_cache
                WHERE session_id = ? AND content_hash = ? AND parser = ? AND parser_version = ?
                """,
                (session_id, content_hash, parser, parser_version),
            )
            row = cursor.fetchone()
            return row["raw_result_blob"] if row else None

    def set_parse_cache(
        self,
        session_id: str,
        content_hash: str,
        parser: str,
        parser_version: str,
        raw_result_blob: str,
    ) -> None:
        """Store parsed StructuredDoc JSON into session cache."""
        now_iso = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO parse_cache (
                    session_id, content_hash, parser, parser_version, raw_result_blob, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, content_hash, parser, parser_version, raw_result_blob, now_iso),
            )
            conn.commit()

    def record_document_ingestion(self, session_id: str, pages: int, chunks: int) -> None:
        """Atomically record document ingestion in session usage counters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET docs_count = docs_count + 1,
                    pages_used = pages_used + ?,
                    chunks_embedded = chunks_embedded + ?
                WHERE session_id = ?
                """,
                (pages, chunks, session_id),
            )
            conn.commit()

    def delete_session_data(self, session_id: str) -> None:
        """Cascade delete all records for a session (parents, documents, jobs, cache, session)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM parents WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM documents WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM parse_cache WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
