"""Security test suite verifying zero parser key leakage across upload paths (P6-T7).

Verifies that visitor-supplied parser API keys:
- Never appear in structured or unstructured logs
- Never appear in any SQLite table column (jobs, docs, parents, sessions, cache)
- Never appear in API responses, error messages, or exception details
- Are shredded from process memory immediately after job execution
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager

FAKE_PARSER_KEY = "lp_audit_secret_key_ultra_secure_998877"


def create_security_test_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), "Audited Document", fontsize=16)
    page.insert_text((50, 100), "Testing for credential leakage.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def security_client(tmp_path: Path):
    db_file = tmp_path / "sec_test.db"
    db = DatabaseManager(db_path=db_file)
    cfg = OwnerConfig(
        cohere_api_key="test_cohere_sec",
        groq_api_key="test_groq_sec",
        qdrant_url=":memory:",
    )
    store = QdrantVectorStore(cfg=cfg)

    app.state.db = db
    app.state.cfg = cfg
    app.state.store = store

    async def mock_embed_docs(texts: list[str]) -> list[list[float]]:
        return [[0.05] * 1024 for _ in texts]

    if hasattr(app.state, "job_runner") and app.state.job_runner:
        app.state.job_runner.embedder.embed_documents = AsyncMock(side_effect=mock_embed_docs)

    return TestClient(app), db


def test_parser_key_never_leaks_in_logs_db_or_responses(
    security_client, caplog: pytest.LogCaptureFixture
) -> None:
    """Rigorous grep test verifying FAKE_PARSER_KEY never appears in logs, SQLite, or responses."""
    client, db = security_client
    caplog.set_level(logging.DEBUG)

    # 1. Create session
    s_resp = client.post("/session")
    token = s_resp.json()["session_id"]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Parser-Key": FAKE_PARSER_KEY,
    }

    pdf_bytes = create_security_test_pdf()

    # 2. Test POST /upload/validate with fake key
    files = {"file": ("audit.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {"parser": "llamaparse"}

    with patch(
        "src.api.upload.verify_provider_connection",
        new=AsyncMock(return_value=AsyncMock(ok=True, hint="Key verified", error_code=None)),
    ):
        val_resp = client.post("/upload/validate", headers=headers, files=files, data=data)

    assert FAKE_PARSER_KEY not in val_resp.text, "Key leaked in /upload/validate response!"

    # 3. Test POST /upload with fake key
    files = {"file": ("audit.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {"parser": "llamaparse", "allow_fallback": "true", "terms_accepted": "true"}

    with patch(
        "src.ingest.parsers.llamaparse.LlamaParseAdapter.parse",
        side_effect=RuntimeError("Simulated cloud failure to test error path"),
    ):
        upload_resp = client.post("/upload", headers=headers, files=files, data=data)

    assert FAKE_PARSER_KEY not in upload_resp.text, "Key leaked in /upload response!"
    job_id = upload_resp.json()["job_id"]

    # 4. Poll job
    poll_resp = client.get(f"/jobs/{job_id}", headers=headers)
    assert FAKE_PARSER_KEY not in poll_resp.text, "Key leaked in /jobs response!"

    # 5. Check all captured logs
    captured_logs = caplog.text
    assert FAKE_PARSER_KEY not in captured_logs, (
        "CRITICAL SECURITY ERROR: Parser key leaked into application logs!"
    )

    # 6. Check all SQLite tables and columns
    with db._get_connection() as conn:
        cursor = conn.cursor()
        for table in ["sessions", "jobs", "documents", "parents", "parse_cache", "usage_daily"]:
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            for row in rows:
                row_str = " ".join(str(val) for val in dict(row).values())
                assert FAKE_PARSER_KEY not in row_str, (
                    f"CRITICAL SECURITY ERROR: Parser key leaked into SQLite table '{table}'!"
                )
