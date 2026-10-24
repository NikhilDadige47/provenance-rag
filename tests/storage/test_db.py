"""Unit tests and security audits for SQLite metadata storage."""

import sqlite3

from src.ingest.chunking.models import ParentChunk
from src.storage.db import DatabaseManager


def test_sqlite_schema_zero_secret_audit(tmp_path):
    """CRITICAL SECURITY AUDIT: Verify no SQL table contains key or secret columns."""
    db_file = tmp_path / "audit_test.db"
    DatabaseManager(db_path=db_file)

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]

    forbidden_substrings = ["key", "token", "secret", "password", "auth", "credential"]

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [row[1].lower() for row in cursor.fetchall()]
        for col in columns:
            # Exempt usage/token counters like owner_tokens_used or token_count
            if col in ("token_count", "owner_tokens_used", "owner_llm_tokens"):
                continue
            for forbidden in forbidden_substrings:
                assert forbidden not in col, (
                    f"Forbidden credential column '{col}' detected in table '{table}'!"
                )
    conn.close()


def test_parent_chunk_storage_and_scope_isolation(tmp_path):
    """Verify parents are inserted and fetched strictly with matching session or demo scope."""
    db_file = tmp_path / "parent_test.db"
    db = DatabaseManager(db_path=db_file)

    parent_alpha = ParentChunk(
        parent_id="p_alpha_1",
        doc_id="doc_alpha",
        breadcrumb="Doc Alpha > Section 1",
        text="Alpha secret parent text.",
        token_count=100,
        page_start=1,
        page_end=2,
    )

    parent_demo = ParentChunk(
        parent_id="p_demo_1",
        doc_id="doc_demo",
        breadcrumb="Demo > Public",
        text="Public demo parent text.",
        token_count=80,
        page_start=1,
        page_end=1,
    )

    db.insert_parents([parent_alpha], session_id="session_alpha")
    db.insert_parents([parent_demo], session_id="demo")

    # Alpha session can fetch its own parent
    res = db.get_parent("p_alpha_1", scope="session_alpha")
    assert res is not None
    assert res["text"] == "Alpha secret parent text."

    # Beta session CANNOT fetch alpha's parent!
    res_forbidden = db.get_parent("p_alpha_1", scope="session_beta")
    assert res_forbidden is None

    # Any session can fetch demo parent
    res_demo = db.get_parent("p_demo_1", scope="session_alpha")
    assert res_demo is not None
    assert res_demo["text"] == "Public demo parent text."


def test_session_usage_tracking(tmp_path):
    """Verify session creation and financial usage counter increments."""
    db_file = tmp_path / "session_test.db"
    db = DatabaseManager(db_path=db_file)

    session = db.create_or_get_session("sess_user_1", tier="tier_b")
    assert session["session_id"] == "sess_user_1"
    assert session["tier"] == "tier_b"

    db.increment_session_usage("sess_user_1", chunks_embedded=45, rerank_calls=3)

    session_updated = db.create_or_get_session("sess_user_1")
    assert session_updated["chunks_embedded"] == 45
    assert session_updated["rerank_calls"] == 3
