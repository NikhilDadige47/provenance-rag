"""Unit tests and security audits for SQLite metadata storage."""

import sqlite3

import pytest

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


def test_parents_require_document_when_foreign_keys_on(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "fk_order.db")
    db.create_or_get_session("sess_fk")
    parent = ParentChunk(
        parent_id="p_fk_1",
        doc_id="doc_fk",
        breadcrumb="Doc > Section",
        text="Parent text.",
        token_count=10,
        page_start=1,
        page_end=1,
    )
    with pytest.raises(Exception, match="FOREIGN KEY|constraint"):
        db.insert_parents([parent], session_id="sess_fk")
    db.insert_document("doc_fk", "sess_fk", "Doc", "h_fk", 1, "local_pymupdf")
    db.insert_parents([parent], session_id="sess_fk")
    assert db.get_parent("p_fk_1", scope="sess_fk") is not None


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

    db.create_or_get_session("session_alpha")
    db.create_or_get_session("demo")
    db.insert_document("doc_alpha", "session_alpha", "Doc Alpha", "h_alpha", 2, "local_pymupdf")
    db.insert_document("doc_demo", "demo", "Demo", "h_demo", 1, "local_pymupdf")
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


def test_resolve_default_db_path_uses_data_dir(tmp_path, monkeypatch):
    from src.storage.db import DatabaseManager, resolve_default_db_path

    data_dir = tmp_path / "persist"
    monkeypatch.delenv("SQLITE_PATH", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    path = resolve_default_db_path(data_dir=str(data_dir))
    assert path == data_dir / "provenance_rag.db"
    db = DatabaseManager(db_path=path)
    db.create_or_get_session("sess_disk")
    assert path.is_file()


def test_sql_row_supports_dict_and_index():
    from src.storage.sql import SqlRow

    row = SqlRow(("prov_sess_abc", "tier_a_demo"), ["session_id", "tier"])
    assert dict(row)["session_id"] == "prov_sess_abc"
    assert row["tier"] == "tier_a_demo"
    assert row[0] == "prov_sess_abc"


def test_mapping_cursor_wraps_tuple_rows():
    from src.storage.sql import SqlRow, _MappingCursor

    class FakeCursor:
        description = (("session_id",), ("tier",))

        def fetchone(self):
            return ("prov_sess_abc", "tier_a_demo")

    row = _MappingCursor(FakeCursor()).fetchone()
    assert isinstance(row, SqlRow)
    assert dict(row)["session_id"] == "prov_sess_abc"
    assert row["tier"] == "tier_a_demo"


def test_open_sql_connection_uses_turso_when_url_set(monkeypatch, tmp_path):
    import sys

    from src.storage import sql as sqlmod

    captured: dict = {}

    class FakeConn:
        row_factory = None

        def execute(self, *_a, **_k):
            return self

    def fake_connect(*, database, auth_token):
        captured["database"] = database
        captured["auth_token"] = auth_token
        return FakeConn()

    fake_libsql = type("libsql", (), {"connect": staticmethod(fake_connect)})
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://demo.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "tok_test")
    monkeypatch.setitem(sys.modules, "libsql", fake_libsql)
    conn = sqlmod.open_sql_connection(str(tmp_path / "ignored.db"))
    assert captured["database"] == "libsql://demo.turso.io"
    assert captured["auth_token"] == "tok_test"
    assert isinstance(conn._conn, FakeConn)


def test_list_incomplete_jobs(tmp_path):
    from src.storage.db import DatabaseManager

    db = DatabaseManager(db_path=tmp_path / "jobs.db")
    db.create_or_get_session("sess_1")
    db.create_job("job_queued", "sess_1", "local_pymupdf", status="queued")
    db.create_job("job_ready", "sess_1", "local_pymupdf", status="ready")
    db.update_job("job_ready", status="ready")
    incomplete = db.list_incomplete_jobs()
    ids = {row["job_id"] for row in incomplete}
    assert "job_queued" in ids
    assert "job_ready" not in ids
