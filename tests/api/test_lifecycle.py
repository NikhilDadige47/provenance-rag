"""Tests for data lifecycle management, DELETE /session, document deletion, and TTL janitor (P6-T6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.api.lifecycle import delete_document, delete_session, purge_expired_sessions
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager


@pytest.fixture
def lifecycle_env(tmp_path: Path):
    db_file = tmp_path / "test_lifecycle.db"
    db = DatabaseManager(db_path=db_file)
    cfg = OwnerConfig(
        cohere_api_key="test_cohere_key",
        groq_api_key="test_groq_key",
        qdrant_url=":memory:",
    )
    store = QdrantVectorStore(cfg=cfg)
    return db, store, cfg


def test_delete_session_wipes_all_data(lifecycle_env) -> None:
    """Verify delete_session completely purges vectors, parents, documents, jobs, and cache."""
    db, store, cfg = lifecycle_env
    session_id = "session_purge_1"
    doc_id = "doc_purge_1"

    # Seed session and document data
    db.create_or_get_session(session_id, tier="tier_b")
    db.create_job("job_p1", session_id, "local_pymupdf", doc_id=doc_id, status="ready")
    db.insert_document(
        doc_id=doc_id,
        session_id=session_id,
        title="Sensitive Contract",
        content_hash="abc123hash",
        page_count=5,
        parser_used="local_pymupdf",
    )
    db.set_parse_cache(
        session_id=session_id,
        content_hash="abc123hash",
        parser="local_pymupdf",
        parser_version="1.0",
        raw_result_blob='{"blocks": []}',
    )

    # Insert a dummy point in Qdrant under this session scope
    from qdrant_client.models import PointStruct, SparseVector

    store._client.upsert(
        collection_name=store.collection_name,
        points=[
            PointStruct(
                id=12345,
                vector={
                    "dense": [0.1] * 1024,
                    "sparse": SparseVector(indices=[1], values=[1.0]),
                },
                payload={"scope": session_id, "doc_id": doc_id},
            )
        ],
    )

    # Ensure point exists
    res = store.hybrid_search(dense_query=[0.1] * 1024, scope=session_id, limit=5)
    assert len(res) == 1

    # Execute hard deletion
    result = delete_session(session_id=session_id, db=db, store=store)
    assert result["status"] == "deleted"

    # Verify Qdrant points are gone
    res_after = store.hybrid_search(dense_query=[0.1] * 1024, scope=session_id, limit=5)
    assert len(res_after) == 0

    # Verify SQLite rows are gone
    assert db.get_session(session_id) is None
    assert db.get_document(doc_id) is None
    assert db.get_job("job_p1") is None
    assert (
        db.get_parse_cache(
            session_id=session_id,
            content_hash="abc123hash",
            parser="local_pymupdf",
            parser_version="1.0",
        )
        is None
    )


def test_delete_single_document(lifecycle_env) -> None:
    """Verify deleting one document removes its vectors and SQL record but keeps session."""
    db, store, cfg = lifecycle_env
    session_id = "session_doc_del"
    doc1 = "doc_del_1"
    doc2 = "doc_keep_2"

    db.create_or_get_session(session_id, tier="tier_b")
    db.insert_document(doc1, session_id, "Doc 1", "h1", 2, "local_pymupdf")
    db.insert_document(doc2, session_id, "Doc 2", "h2", 3, "local_pymupdf")

    from qdrant_client.models import PointStruct, SparseVector

    store._client.upsert(
        collection_name=store.collection_name,
        points=[
            PointStruct(
                id=111,
                vector={"dense": [0.1] * 1024, "sparse": SparseVector(indices=[1], values=[1.0])},
                payload={"scope": session_id, "doc_id": doc1},
            ),
            PointStruct(
                id=222,
                vector={"dense": [0.1] * 1024, "sparse": SparseVector(indices=[1], values=[1.0])},
                payload={"scope": session_id, "doc_id": doc2},
            ),
        ],
    )

    del_res = delete_document(doc_id=doc1, session_id=session_id, db=db, store=store)
    assert del_res["status"] == "deleted"

    # Doc 1 gone
    assert db.get_document(doc1) is None
    # Doc 2 still exists
    assert db.get_document(doc2) is not None
    # Session still exists
    assert db.get_session(session_id) is not None


def test_purge_expired_sessions(lifecycle_env) -> None:
    """Verify TTL janitor identifies and wipes sessions past their expires_at."""
    db, store, cfg = lifecycle_env

    now = datetime.now(UTC)
    past_iso = (now - timedelta(hours=3)).isoformat()
    future_iso = (now + timedelta(hours=2)).isoformat()

    # Expired session
    with db._get_connection() as conn:
        conn.cursor().execute(
            """
            INSERT INTO sessions (session_id, created_at, expires_at, tier)
            VALUES ('session_expired_old', ?, ?, 'tier_b')
            """,
            (past_iso, past_iso),
        )
        # Active session
        conn.cursor().execute(
            """
            INSERT INTO sessions (session_id, created_at, expires_at, tier)
            VALUES ('session_active_now', ?, ?, 'tier_b')
            """,
            (now.isoformat(), future_iso),
        )
        conn.commit()

    purged = purge_expired_sessions(db=db, store=store)
    assert "session_expired_old" in purged
    assert "session_active_now" not in purged

    # Verify expired session is gone, active remains
    assert db.get_session("session_expired_old") is None
    assert db.get_session("session_active_now") is not None
