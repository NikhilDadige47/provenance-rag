"""P9-T3: provider, job, and store failure drills with friendly errors."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf
import pytest
from fastapi.testclient import TestClient

from src.api.jobs import JobRunner
from src.api.main import app
from src.retrieval.search import SearchResult
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.security.errors import (
    InvalidKeyError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.storage.db import DatabaseManager


def _pdf_bytes() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), "Failure Drill", fontsize=16)
    page.insert_text((50, 110), "Revenue increased year over year.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def job_env(tmp_path: Path):
    db = DatabaseManager(db_path=tmp_path / "fail.db")
    db.create_or_get_session("session_job_1", tier="tier_b")
    cfg = OwnerConfig(
        qdrant_url=":memory:",
        landingai_api_key=None,
        llamaparse_api_key=None,
    )
    store = QdrantVectorStore(cfg=cfg)
    runner = JobRunner(db=db, store=store, cfg=cfg, job_timeout_seconds=0.2)
    runner.embedder.embed_documents = AsyncMock(return_value=[[0.05] * 1024])
    runner.embedder.embed = AsyncMock(return_value=[[0.05] * 1024])
    return db, store, runner, cfg


@pytest.mark.asyncio
async def test_job_timeout_marks_failed_and_rolls_back(job_env) -> None:
    db, store, runner, _cfg = job_env
    job_id = "job_timeout"
    db.create_job(job_id=job_id, session_id="session_job_1", parser_name="local_pymupdf")

    async def hang(*_a, **_k):
        await asyncio.sleep(2)

    with patch.object(runner, "_parse_with_fallback", new=hang):
        await runner.run_ingestion_pipeline(
            job_id=job_id,
            session_id="session_job_1",
            filename="t.pdf",
            file_bytes=_pdf_bytes(),
            parser_name="local_pymupdf",
        )

    job = db.get_job(job_id, session_id="session_job_1")
    assert job["status"] == "failed"
    assert "timed out" in (job.get("error_message") or "").lower()


@pytest.mark.asyncio
async def test_cancelled_job_fails_cleanly(job_env) -> None:
    db, store, runner, _cfg = job_env
    job_id = "job_cancel"
    db.create_job(job_id=job_id, session_id="session_job_1", parser_name="local_pymupdf")

    async def hang(*_a, **_k):
        await asyncio.sleep(30)

    with patch.object(runner, "_parse_with_fallback", new=hang):
        task = runner.spawn_ingestion_pipeline(
            job_id=job_id,
            session_id="session_job_1",
            filename="t.pdf",
            file_bytes=_pdf_bytes(),
            parser_name="local_pymupdf",
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    job = db.get_job(job_id, session_id="session_job_1")
    assert job["status"] == "failed"
    assert "cancel" in (job.get("error_message") or "").lower() or "timed out" in (
        job.get("error_message") or ""
    ).lower()


@pytest.mark.asyncio
async def test_embed_outage_fails_job_without_stack(job_env) -> None:
    db, _store, runner, _cfg = job_env
    job_id = "job_embed_down"
    db.create_job(job_id=job_id, session_id="session_job_1", parser_name="local_pymupdf")
    runner.embedder.embed_documents = AsyncMock(
        side_effect=ProviderUnavailableError(provider="cohere", status_code=503)
    )
    await runner.run_ingestion_pipeline(
        job_id=job_id,
        session_id="session_job_1",
        filename="t.pdf",
        file_bytes=_pdf_bytes(),
        parser_name="local_pymupdf",
    )
    job = db.get_job(job_id, session_id="session_job_1")
    assert job["status"] == "failed"
    assert "unavailable" in (job.get("error_message") or "").lower()
    assert "Traceback" not in (job.get("error_message") or "")


@pytest.mark.asyncio
async def test_parser_invalid_key_no_retry(job_env) -> None:
    db, _store, runner, _cfg = job_env
    job_id = "job_bad_key"
    db.create_job(job_id=job_id, session_id="session_job_1", parser_name="llamaparse")

    async def boom(*_a, **_k):
        raise InvalidKeyError(provider="llamaparse", is_visitor_key=True)

    with patch.object(runner, "_parse_with_fallback", new=boom):
        await runner.run_ingestion_pipeline(
            job_id=job_id,
            session_id="session_job_1",
            filename="t.pdf",
            file_bytes=_pdf_bytes(),
            parser_name="llamaparse",
            parser_key="lp_bad",
            allow_fallback=False,
        )
    job = db.get_job(job_id, session_id="session_job_1")
    assert job["status"] == "failed"
    assert "rejected" in (job.get("error_message") or "").lower()


@pytest.mark.asyncio
async def test_parser_quota_and_timeout_messages(job_env) -> None:
    _db, _store, runner, _cfg = job_env
    assert "quota" in runner._format_error(QuotaExhaustedError("llamaparse")).lower()
    assert "rate-limited" in runner._format_error(RateLimitedError("llamaparse")).lower()
    assert "timed out" in runner._format_error(ProviderTimeoutError("llamaparse")).lower()


def test_qdrant_outage_returns_search_unavailable(tmp_path: Path) -> None:
    db = DatabaseManager(db_path=tmp_path / "chat_fail.db")
    cfg = OwnerConfig(qdrant_url=":memory:")
    store = QdrantVectorStore(cfg=cfg)
    app.state.db = db
    app.state.cfg = cfg
    app.state.store = store
    token = None
    client = TestClient(app, raise_server_exceptions=False)
    token = client.post("/session").json()["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    async def boom(*_a, **_k):
        raise ConnectionError("qdrant down")

    with patch("src.api.chat.HybridSearchPipeline.search", new=AsyncMock(side_effect=boom)):
        resp = client.post("/chat", json={"question": "What is net sales?", "history": []}, headers=headers)
    assert resp.status_code == 503
    assert "search" in resp.json()["detail"].lower()


def test_llm_outage_is_friendly(tmp_path: Path) -> None:
    db = DatabaseManager(db_path=tmp_path / "llm_fail.db")
    cfg = OwnerConfig(qdrant_url=":memory:")
    store = QdrantVectorStore(cfg=cfg)
    app.state.db = db
    app.state.cfg = cfg
    app.state.store = store
    client = TestClient(app, raise_server_exceptions=False)
    token = client.post("/session").json()["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    found = SearchResult(
        query="q",
        scope="demo",
        chunks=[],
        is_found=True,
        reason=None,
    )
    # is_found True with empty chunks still proceeds to generate; patch generate_stream.

    class FakeLLM:
        provider_name = "groq"
        _model = "test"

        async def generate_stream(self, *_a, **_k):
            raise ProviderUnavailableError(provider="groq", status_code=503)
            yield  # pragma: no cover

    async def fake_search(*_a, **_k):
        return found

    with (
        patch("src.api.chat.HybridSearchPipeline.search", new=AsyncMock(side_effect=fake_search)),
        patch("src.api.chat.get_llm_adapter", return_value=FakeLLM()),
        patch("src.api.chat.ContextExpander.expand", return_value=type("R", (), {"passages": []})()),
        patch("src.api.chat.build_generation_prompt", return_value=("sys", "user")),
        patch("src.api.chat.reserve_owner_llm_tokens", new=AsyncMock(return_value=[])),
        patch("src.api.chat.audit_citations") as audit,
    ):
        audit.return_value = type("A", (), {"is_grounded": False, "sources": []})()
        resp = client.post("/chat", json={"question": "What is net sales?", "history": []}, headers=headers)

    assert resp.status_code == 200
    assert "unavailable" in resp.json()["answer"].lower()
