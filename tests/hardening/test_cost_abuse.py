"""P9-T1 / P9-T2: caps, kill switch, and daily upload limits hold under abuse."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.caps import (
    MAX_DAILY_UPLOADS_PER_IP,
    MAX_REQUESTS_PER_WINDOW,
    check_and_increment_daily_jobs,
    check_ip_daily_upload_limit,
    check_ip_rate_limit,
    increment_ip_daily_uploads,
    reset_ip_limiters,
)
from src.api.jobs import DEFAULT_MAX_QUEUED, JobRunner
from src.api.main import app
from src.retrieval.search import SearchResult
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager


def _pdf_bytes(title: str = "Abuse") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), title, fontsize=16)
    page.insert_text((50, 100), "Abuse-test paragraph.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def isolated_app(tmp_path: Path):
    reset_ip_limiters()
    db = DatabaseManager(db_path=tmp_path / "abuse.db")
    cfg = OwnerConfig(
        session_max_questions_owner_llm=3,
        daily_max_jobs=2,
        daily_max_rerank_calls=500,
        qdrant_url=":memory:",
        landingai_api_key=None,
        llamaparse_api_key=None,
    )
    store = QdrantVectorStore(cfg=cfg)
    runner = JobRunner(db=db, store=store, cfg=cfg)
    runner.embedder.embed_documents = AsyncMock(return_value=[[0.05] * 1024])
    runner.embedder.embed = AsyncMock(return_value=[[0.05] * 1024])
    app.state.db = db
    app.state.cfg = cfg
    app.state.store = store
    app.state.job_runner = runner
    yield TestClient(app, raise_server_exceptions=False), db, cfg
    reset_ip_limiters()


def _session(client: TestClient) -> dict[str, str]:
    token = client.post("/session").json()["session_id"]
    return {"Authorization": f"Bearer {token}"}


async def _empty_search(*_args, **_kwargs) -> SearchResult:
    return SearchResult(query="q", scope="demo", chunks=[], is_found=False, reason="test")


class TestOwnerQuestionCapBlocksPaidPath:
    def test_sixteenth_owner_question_is_429(self, isolated_app) -> None:
        client, _db, cfg = isolated_app
        headers = _session(client)
        with patch("src.api.chat.HybridSearchPipeline.search", new=AsyncMock(side_effect=_empty_search)):
            for _ in range(cfg.session_max_questions_owner_llm):
                resp = client.post("/chat", json={"question": "What is net sales?", "history": []}, headers=headers)
                assert resp.status_code == 200
            blocked = client.post("/chat", json={"question": "What is net sales?", "history": []}, headers=headers)
        assert blocked.status_code == 429
        assert "owner-funded" in blocked.json()["detail"].lower()

    def test_new_session_same_ip_does_not_reset_budget(self, isolated_app) -> None:
        client, _db, cfg = isolated_app
        headers = _session(client)
        with patch("src.api.chat.HybridSearchPipeline.search", new=AsyncMock(side_effect=_empty_search)):
            for _ in range(cfg.session_max_questions_owner_llm):
                resp = client.post("/chat", json={"question": "What is net sales?", "history": []}, headers=headers)
                assert resp.status_code == 200
            other = _session(client)
            blocked = client.post(
                "/chat", json={"question": "What is net sales?", "history": []}, headers=other
            )
        assert blocked.status_code == 429

    def test_cookie_resume_keeps_same_session(self, isolated_app) -> None:
        client, _db, _cfg = isolated_app
        created = client.post("/session")
        token = created.json()["session_id"]
        resumed = client.get("/session")
        assert resumed.status_code == 200
        assert resumed.json()["session_id"] == token

    def test_usage_meter_stays_exhausted_on_new_session(self, isolated_app) -> None:
        client, _db, cfg = isolated_app
        headers = _session(client)
        with patch("src.api.chat.HybridSearchPipeline.search", new=AsyncMock(side_effect=_empty_search)):
            for _ in range(cfg.session_max_questions_owner_llm):
                resp = client.post(
                    "/chat", json={"question": "What is net sales?", "history": []}, headers=headers
                )
                assert resp.status_code == 200
        other = _session(client)
        usage = client.get("/usage", headers=other)
        assert usage.status_code == 200
        body = usage.json()
        assert body["questions_owner_llm_remaining"] == 0
        assert body["owner_questions_exhausted"] is True

    def test_spoofed_forwarded_for_does_not_reset_dev_budget(self, isolated_app) -> None:
        client, _db, cfg = isolated_app
        headers = _session(client)
        with patch("src.api.chat.HybridSearchPipeline.search", new=AsyncMock(side_effect=_empty_search)):
            for _ in range(cfg.session_max_questions_owner_llm):
                resp = client.post(
                    "/chat", json={"question": "What is net sales?", "history": []}, headers=headers
                )
                assert resp.status_code == 200
            spoofed = {
                **headers,
                "X-Forwarded-For": "203.0.113.77",
            }
            blocked = client.post(
                "/chat", json={"question": "What is net sales?", "history": []}, headers=spoofed
            )
        assert blocked.status_code == 429


class TestKillSwitchUnderLoad:
    def test_owner_llm_kill_switch_returns_503(self, isolated_app) -> None:
        client, _db, cfg = isolated_app
        cfg.kill_switch_disable_owner_llm = True
        headers = _session(client)
        resp = client.post("/chat", json={"question": "What is net sales?", "history": []}, headers=headers)
        assert resp.status_code == 503
        assert "disabled" in resp.json()["detail"].lower()

    def test_upload_kill_switch_keeps_demo_chat(self, isolated_app) -> None:
        client, _db, cfg = isolated_app
        cfg.kill_switch_disable_uploads = True
        headers = _session(client)
        files = {"file": ("a.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
        up = client.post(
            "/upload",
            headers=headers,
            files=files,
            data={"parser": "local_pymupdf", "terms_accepted": "true"},
        )
        assert up.status_code == 503
        with patch("src.api.chat.HybridSearchPipeline.search", new=AsyncMock(side_effect=_empty_search)):
            chat = client.post("/chat", json={"question": "What is net sales?", "history": []}, headers=headers)
        assert chat.status_code == 200


class TestIPLimits:
    def test_rate_limit_trips_at_window_max(self) -> None:
        reset_ip_limiters()
        ip = "198.51.100.9"
        for _ in range(MAX_REQUESTS_PER_WINDOW):
            check_ip_rate_limit(ip)
        with pytest.raises(HTTPException) as exc:
            check_ip_rate_limit(ip)
        assert exc.value.status_code == 429
        reset_ip_limiters()

    def test_daily_upload_cap_trips(self, tmp_path: Path) -> None:
        db = DatabaseManager(db_path=tmp_path / "ip_uploads.db")
        ip = "198.51.100.10"
        for _ in range(MAX_DAILY_UPLOADS_PER_IP):
            check_ip_daily_upload_limit(db, ip)
            increment_ip_daily_uploads(db, ip)
        with pytest.raises(HTTPException) as exc:
            check_ip_daily_upload_limit(db, ip)
        assert exc.value.status_code == 429
        assert "upload" in exc.value.detail.lower()


class TestDailyJobCap:
    def test_daily_jobs_trigger_capacity(self, tmp_path: Path) -> None:
        db = DatabaseManager(db_path=tmp_path / "jobs_cap.db")
        cfg = OwnerConfig(daily_max_jobs=1)
        check_and_increment_daily_jobs(db, cfg)
        with pytest.raises(HTTPException) as exc:
            check_and_increment_daily_jobs(db, cfg)
        assert exc.value.status_code == 429
        assert "capacity" in exc.value.detail.lower()


class TestTermsGate:
    def test_terms_rejected(self, isolated_app) -> None:
        client, _db, _cfg = isolated_app
        headers = _session(client)
        files = {"file": ("a.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
        resp = client.post(
            "/upload",
            headers=headers,
            files=files,
            data={"parser": "local_pymupdf", "terms_accepted": "false"},
        )
        assert resp.status_code == 400
        assert "terms" in resp.json()["detail"].lower()

    def test_terms_required_when_omitted(self, isolated_app) -> None:
        client, _db, _cfg = isolated_app
        headers = _session(client)
        files = {"file": ("a.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
        resp = client.post(
            "/upload",
            headers=headers,
            files=files,
            data={"parser": "local_pymupdf"},
        )
        assert resp.status_code == 400
        assert "terms" in resp.json()["detail"].lower()


class TestConcurrentJobCap:
    def test_queue_full_returns_429(self, isolated_app) -> None:
        client, _db, _cfg = isolated_app
        headers = _session(client)
        runner = app.state.job_runner
        previous_tasks = set(runner._tasks)
        previous_max = runner._max_concurrency
        previous_queued = runner._max_queued
        try:
            runner._max_concurrency = 1
            runner._max_queued = DEFAULT_MAX_QUEUED
            for _ in range(runner._max_concurrency + runner._max_queued):
                runner._tasks.add(object())  # type: ignore[arg-type]
            files = {"file": ("a.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
            resp = client.post(
                "/upload",
                headers=headers,
                files=files,
                data={"parser": "local_pymupdf", "terms_accepted": "true"},
            )
            assert resp.status_code == 429
            assert "processed" in resp.json()["detail"].lower()
        finally:
            runner._tasks = previous_tasks
            runner._max_concurrency = previous_max
            runner._max_queued = previous_queued
