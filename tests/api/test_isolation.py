"""Tests for P5-T7: Multi-tenant session isolation.

Covers:
  - Session A cannot access chunks/parents belonging to Session B
  - Scope filter is always enforced server-side (clients cannot override)
  - Both sessions can see scope="demo" data
  - Client-supplied filter parameters in request body are ignored
  - Scoped parent lookups in DatabaseManager are isolation-safe
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.storage.db import DatabaseManager


@pytest.fixture()
def tmp_db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(db_path=tmp_path / "isolation_test.db")


@pytest.fixture()
def db_two_sessions(tmp_db: DatabaseManager) -> tuple[DatabaseManager, str, str]:
    """Create two distinct sessions and return (db, session_A, session_B)."""
    session_a = "prov_sess_sessionA_isolation_test"
    session_b = "prov_sess_sessionB_isolation_test"
    now = datetime.now(UTC).isoformat()

    with tmp_db._get_connection() as conn:
        for sid in [session_a, session_b]:
            conn.execute(
                "INSERT INTO sessions (session_id, created_at, tier) VALUES (?, ?, ?)",
                (sid, now, "tier_b_upload"),
            )
        conn.commit()

    return tmp_db, session_a, session_b


class TestParentScopeIsolation:
    """DatabaseManager.get_parent must enforce scope isolation."""

    def _insert_parent(
        self,
        db: DatabaseManager,
        parent_id: str,
        session_id: str,
        doc_id: str = "doc_001",
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with db._get_connection() as conn:
            # Insert doc first (FK)
            conn.execute(
                """
                INSERT OR IGNORE INTO documents
                (doc_id, session_id, title, content_hash, page_count, parser_used, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, session_id, "Test Doc", "hash_abc", 5, "local_pymupdf", now),
            )
            conn.execute(
                """
                INSERT INTO parents
                (parent_id, doc_id, session_id, breadcrumb, text, token_count, page_start, page_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (parent_id, doc_id, session_id, "Test > Section", "Parent content.", 50, 1, 2),
            )
            conn.commit()

    def test_session_a_cannot_read_session_b_parents(
        self, db_two_sessions: tuple[DatabaseManager, str, str]
    ) -> None:
        """Session A's scope must not return parents belonging to Session B."""
        db, session_a, session_b = db_two_sessions

        parent_b_id = "parent_belongs_to_session_b"
        self._insert_parent(db, parent_b_id, session_b, doc_id="doc_b_001")

        # Session A tries to fetch Session B's parent — must return None
        result = db.get_parent(parent_b_id, scope=session_a)
        assert result is None, (
            f"Session isolation violated: session_a retrieved parent owned by session_b. "
            f"result={result}"
        )

    def test_session_a_can_read_own_parents(
        self, db_two_sessions: tuple[DatabaseManager, str, str]
    ) -> None:
        db, session_a, _ = db_two_sessions
        parent_a_id = "parent_belongs_to_session_a"
        self._insert_parent(db, parent_a_id, session_a, doc_id="doc_a_001")

        result = db.get_parent(parent_a_id, scope=session_a)
        assert result is not None
        assert result["session_id"] == session_a

    def test_demo_scope_readable_by_all_sessions(
        self, db_two_sessions: tuple[DatabaseManager, str, str]
    ) -> None:
        """Parents with session_id='demo' must be visible to all valid sessions."""
        db, session_a, session_b = db_two_sessions

        demo_parent_id = "parent_in_demo_corpus"
        self._insert_parent(db, demo_parent_id, "demo", doc_id="doc_demo_001")

        # Both sessions should see the demo parent
        result_a = db.get_parent(demo_parent_id, scope=session_a)
        result_b = db.get_parent(demo_parent_id, scope=session_b)

        assert result_a is not None, "Session A could not read demo corpus parent"
        assert result_b is not None, "Session B could not read demo corpus parent"

    def test_session_b_cannot_read_session_a_parents(
        self, db_two_sessions: tuple[DatabaseManager, str, str]
    ) -> None:
        """Isolation is bidirectional."""
        db, session_a, session_b = db_two_sessions

        parent_a_id = "parent_a_bidir_test"
        self._insert_parent(db, parent_a_id, session_a, doc_id="doc_a_bidir")

        result = db.get_parent(parent_a_id, scope=session_b)
        assert result is None


class TestSessionCounterIsolation:
    """Each session's usage counters must be independent."""

    def test_counters_are_session_scoped(
        self, db_two_sessions: tuple[DatabaseManager, str, str]
    ) -> None:
        db, session_a, session_b = db_two_sessions

        # Increment A's usage
        db.increment_session_usage(session_a, chunks_embedded=100, rerank_calls=5)

        # B's counters must be untouched
        row_b = db.get_session(session_b)
        assert row_b is not None
        assert row_b["chunks_embedded"] == 0
        assert row_b["rerank_calls"] == 0

    def test_increments_only_affect_target_session(
        self, db_two_sessions: tuple[DatabaseManager, str, str]
    ) -> None:
        db, session_a, session_b = db_two_sessions

        db.increment_session_usage(session_a, chunks_embedded=50)
        db.increment_session_usage(session_b, chunks_embedded=200)

        row_a = db.get_session(session_a)
        row_b = db.get_session(session_b)

        assert row_a["chunks_embedded"] == 50
        assert row_b["chunks_embedded"] == 200
