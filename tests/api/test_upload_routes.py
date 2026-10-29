"""Integration tests for FastAPI upload, job polling, and lifecycle endpoints."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock

import pymupdf
import pytest
from fastapi.testclient import TestClient

from src.api.jobs import JobRunner
from src.api.main import app
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager


def _upload_form(**fields: str) -> dict[str, str]:
    data = {"terms_accepted": "true"}
    data.update(fields)
    return data


def create_minimal_pdf_bytes(title: str = "Test") -> bytes:
    doc = pymupdf.open()
    doc.set_metadata({"title": title})
    page = doc.new_page()
    page.insert_text((50, 70), "Heading One", fontsize=16)
    page.insert_text((50, 100), "Sample text content for route testing.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def client(tmp_path: Path):
    db_file = tmp_path / "test_routes.db"
    db = DatabaseManager(db_path=db_file)
    cfg = OwnerConfig(
        cohere_api_key="test_cohere",
        groq_api_key="test_groq",
        qdrant_url=":memory:",
        landingai_api_key=None,
        llamaparse_api_key=None,
    )
    store = QdrantVectorStore(cfg=cfg)
    job_runner = JobRunner(db=db, store=store, cfg=cfg)

    # Mock embed so background jobs don't call external Cohere API
    async def mock_embed_docs(texts: list[str], *args, **kwargs) -> list[list[float]]:
        return [[0.05] * 1024 for _ in texts]

    job_runner.embedder.embed = AsyncMock(side_effect=mock_embed_docs)
    job_runner.embedder.embed_documents = AsyncMock(side_effect=mock_embed_docs)

    with TestClient(app) as client:
        # Lifespan overwrites app.state; restore the isolated test doubles.
        app.state.db = db
        app.state.cfg = cfg
        app.state.store = store
        app.state.job_runner = job_runner
        yield client


def test_upload_validate_endpoint(client: TestClient) -> None:
    """Test POST /upload/validate returns estimation and page count."""
    # 1. Create a session
    s_resp = client.post("/session")
    token = s_resp.json()["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = create_minimal_pdf_bytes("Estimation Doc")
    files = {"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {"parser": "local_pymupdf"}

    resp = client.post("/upload/validate", headers=headers, files=files, data=data)
    assert resp.status_code == 200
    res_json = resp.json()
    assert res_json["page_count"] == 1
    assert res_json["can_proceed"] is True
    assert res_json["requires_visitor_key"] is False


def test_upload_submit_and_poll_job(client: TestClient) -> None:
    """Test POST /upload submits job, returns 202, and GET /jobs/{id} tracks status."""
    # 1. Create session
    s_resp = client.post("/session")
    token = s_resp.json()["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = create_minimal_pdf_bytes("Upload Route Doc")
    files = {"file": ("upload.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = _upload_form(parser="local_pymupdf", allow_fallback="true")

    # 2. Submit upload
    resp = client.post("/upload", headers=headers, files=files, data=data)
    assert resp.status_code == 202
    job_info = resp.json()
    job_id = job_info["job_id"]
    assert job_info["status"] == "queued"
    assert job_info["page_count"] == 1

    # 3. Poll job status
    poll_resp = client.get(f"/jobs/{job_id}", headers=headers)
    assert poll_resp.status_code == 200
    poll_json = poll_resp.json()
    assert poll_json["job_id"] == job_id
    assert poll_json["status"] in (
        "queued",
        "parsing",
        "chunking",
        "embedding",
        "indexing",
        "ready",
    )
    assert "parser_used" in poll_json
    assert "degraded" in poll_json
    assert isinstance(poll_json["degraded"], bool)


def test_upload_cloud_parser_requires_key(client: TestClient) -> None:
    """Explicit cloud parser without owner key and without visitor key returns 400."""
    s_resp = client.post("/session")
    token = s_resp.json()["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = create_minimal_pdf_bytes("Cloud Parser Doc")
    files = {"file": ("cloud.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = _upload_form(parser="llamaparse")

    resp = client.post("/upload", headers=headers, files=files, data=data)
    assert resp.status_code == 400
    assert "requires an API key" in resp.json()["detail"]


def test_upload_auto_does_not_require_visitor_key(client: TestClient) -> None:
    """parser=auto uses the owner waterfall and accepts uploads with no visitor parser key."""
    s_resp = client.post("/session")
    token = s_resp.json()["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = create_minimal_pdf_bytes("Auto Parser Doc")
    files = {"file": ("auto.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = _upload_form(parser="auto", allow_fallback="true")

    resp = client.post("/upload", headers=headers, files=files, data=data)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["parser_used"] == "auto"


def test_upload_default_parser_is_auto(client: TestClient) -> None:
    """Omitting the parser form field defaults to owner-paid auto waterfall."""
    s_resp = client.post("/session")
    token = s_resp.json()["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = create_minimal_pdf_bytes("Default Parser Doc")
    files = {"file": ("default.pdf", io.BytesIO(pdf_bytes), "application/pdf")}

    resp = client.post("/upload", headers=headers, files=files, data=_upload_form())
    assert resp.status_code == 202
    assert resp.json()["parser_used"] == "auto"


def test_job_isolation_between_sessions(client: TestClient) -> None:
    """Session B cannot view or poll Session A's jobs."""
    # Session A
    s_a = client.post("/session").json()["session_id"]
    h_a = {"Authorization": f"Bearer {s_a}"}

    # Session B
    s_b = client.post("/session").json()["session_id"]
    h_b = {"Authorization": f"Bearer {s_b}"}

    pdf_bytes = create_minimal_pdf_bytes("Session A Doc")
    files = {"file": ("a.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = _upload_form(parser="local_pymupdf")

    resp_a = client.post("/upload", headers=h_a, files=files, data=data)
    job_id_a = resp_a.json()["job_id"]

    # Session A can see it
    assert client.get(f"/jobs/{job_id_a}", headers=h_a).status_code == 200

    # Session B receives 404 Not Found
    resp_b = client.get(f"/jobs/{job_id_a}", headers=h_b)
    assert resp_b.status_code == 404
    assert "not found" in resp_b.json()["detail"].lower()


def test_delete_session_endpoint(client: TestClient) -> None:
    """DELETE /session wipes session data."""
    s_resp = client.post("/session")
    token = s_resp.json()["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    del_resp = client.delete("/session", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Subsequent request using this token should fail with 401
    me_resp = client.get("/session/documents", headers=headers)
    assert me_resp.status_code == 401
