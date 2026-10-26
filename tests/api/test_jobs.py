"""Tests for asynchronous job runner, state machine, key shredder, and fallback (P6-T3, P6-T4, P6-T5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf
import pytest

from src.api.jobs import JobRunner
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.security.errors import InvalidKeyError
from src.storage.db import DatabaseManager


def create_sample_pdf_bytes(title: str = "Quarterly Report") -> bytes:
    """Generate minimal valid PDF bytes with headings."""
    doc = pymupdf.open()
    doc.set_metadata({"title": title})
    page = doc.new_page()
    page.insert_text((50, 70), "Executive Summary", fontsize=18)
    page.insert_text(
        (50, 110),
        "Company quarterly operating revenue increased by 22% year-over-year.",
        fontsize=11,
    )
    page.insert_text((50, 150), "Key Operational Highlights", fontsize=14)
    page.insert_text(
        (50, 180),
        "Infrastructure scaling and multi-tenant security architecture launched.",
        fontsize=11,
    )
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def job_env(tmp_path: Path):
    """Set up database, in-memory Qdrant store, and job runner with mock Cohere embeddings."""
    db_file = tmp_path / "test_jobs.db"
    db = DatabaseManager(db_path=db_file)
    db.create_or_get_session("session_job_1", tier="tier_b")

    cfg = OwnerConfig(
        cohere_api_key="test_cohere_key",
        groq_api_key="test_groq_key",
        qdrant_url=":memory:",
    )
    store = QdrantVectorStore(cfg=cfg)
    runner = JobRunner(db=db, store=store, cfg=cfg)

    # Mock dense embeddings to avoid external API calls in unit tests
    async def mock_embed_documents(texts: list[str]) -> list[list[float]]:
        # Return 1024-dim mock vector for each text
        return [[0.05] * 1024 for _ in texts]

    runner.embedder.embed_documents = AsyncMock(side_effect=mock_embed_documents)

    return db, store, runner, cfg


@pytest.mark.asyncio
async def test_job_runner_happy_path(job_env) -> None:
    """End-to-end test of happy path ingestion pipeline with local parser."""
    db, store, runner, cfg = job_env
    pdf_bytes = create_sample_pdf_bytes("Q3 Report")

    job_id = "job_test_happy"
    db.create_job(job_id=job_id, session_id="session_job_1", parser_name="local_pymupdf")

    await runner.run_ingestion_pipeline(
        job_id=job_id,
        session_id="session_job_1",
        filename="report.pdf",
        file_bytes=pdf_bytes,
        parser_name="local_pymupdf",
    )

    # 1. Job status must be 'ready'
    job = db.get_job(job_id, session_id="session_job_1")
    assert job is not None
    assert job["status"] == "ready"
    assert job["pages"] == 1
    assert job["chunks"] > 0
    assert job["doc_id"] is not None
    assert job["finished_at"] is not None

    # 2. Document record exists
    doc = db.get_document(job["doc_id"], session_id="session_job_1")
    assert doc is not None
    assert doc["title"] == "Q3 Report"
    assert doc["page_count"] == 1

    # 3. Session counters updated
    session_row = db.get_session("session_job_1")
    assert session_row["docs_count"] == 1
    assert session_row["pages_used"] == 1
    assert session_row["chunks_embedded"] > 0

    # 4. Qdrant store has vectors for this scope
    # Perform a dummy search to verify points were indexed
    res = store.hybrid_search(
        dense_query=[0.05] * 1024,
        scope="session_job_1",
        limit=5,
    )
    assert len(res) > 0
    assert res[0]["payload"]["scope"] == "session_job_1"


@pytest.mark.asyncio
async def test_job_runner_fallback_on_cloud_failure(job_env) -> None:
    """If cloud parser fails, runner automatically falls back to local PyMuPDF."""
    db, store, runner, cfg = job_env
    pdf_bytes = create_sample_pdf_bytes("Fallback Test")

    job_id = "job_fallback_1"
    db.create_job(job_id=job_id, session_id="session_job_1", parser_name="llamaparse")

    # Mock LlamaParse adapter to raise a transient network error
    with patch(
        "src.ingest.parsers.llamaparse.LlamaParseAdapter.parse",
        side_effect=RuntimeError("Cloud parsing endpoint timeout"),
    ):
        await runner.run_ingestion_pipeline(
            job_id=job_id,
            session_id="session_job_1",
            filename="fallback.pdf",
            file_bytes=pdf_bytes,
            parser_name="llamaparse",
            parser_key="lp_test_key_fake",
            allow_fallback=True,
        )

    # Pipeline should succeed via local fallback
    job = db.get_job(job_id, session_id="session_job_1")
    assert job is not None
    assert job["status"] == "ready"
    assert job["pages"] == 1
    assert job["chunks"] > 0


@pytest.mark.asyncio
async def test_job_runner_fails_fast_on_invalid_visitor_key(job_env) -> None:
    """Invalid visitor key fails fast without retrying and leaves zero partial data."""
    db, store, runner, cfg = job_env
    pdf_bytes = create_sample_pdf_bytes("Key Error")

    job_id = "job_key_err_1"
    db.create_job(job_id=job_id, session_id="session_job_1", parser_name="llamaparse")

    with patch(
        "src.ingest.parsers.llamaparse.LlamaParseAdapter.parse",
        side_effect=InvalidKeyError("Invalid LlamaParse API key"),
    ):
        await runner.run_ingestion_pipeline(
            job_id=job_id,
            session_id="session_job_1",
            filename="key_err.pdf",
            file_bytes=pdf_bytes,
            parser_name="llamaparse",
            parser_key="lp_bad_key",
            allow_fallback=False,
        )

    job = db.get_job(job_id, session_id="session_job_1")
    assert job is not None
    assert job["status"] == "failed"
    assert "API key was rejected" in job["error_message"]

    # Verify no orphan document left in SQL
    docs = db.list_documents("session_job_1")
    assert len(docs) == 0


@pytest.mark.asyncio
async def test_session_parse_cache_hit(job_env) -> None:
    """Verify session parse cache stores and retrieves StructuredDoc to avoid re-parsing."""
    db, store, runner, cfg = job_env
    pdf_bytes = create_sample_pdf_bytes("Cache Test")

    # Ingest document 1
    job_id1 = "job_cache_1"
    db.create_job(job_id=job_id1, session_id="session_job_1", parser_name="local_pymupdf")
    await runner.run_ingestion_pipeline(
        job_id=job_id1,
        session_id="session_job_1",
        filename="doc.pdf",
        file_bytes=pdf_bytes,
        parser_name="local_pymupdf",
    )

    import hashlib

    c_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Parse cache should now have a record
    cached = db.get_parse_cache(
        session_id="session_job_1",
        content_hash=c_hash,
        parser="local_pymupdf",
        parser_version="1.0",
    )
    assert cached is not None

    # Ingest document 2 with same content
    job_id2 = "job_cache_2"
    db.create_job(job_id=job_id2, session_id="session_job_1", parser_name="local_pymupdf")

    # Mock the parser so if it were called, it would fail
    with patch(
        "src.ingest.parsers.local_pymupdf.LocalPyMuPDFParser.parse",
        side_effect=AssertionError("Should have hit cache!"),
    ):
        await runner.run_ingestion_pipeline(
            job_id=job_id2,
            session_id="session_job_1",
            filename="doc_copy.pdf",
            file_bytes=pdf_bytes,
            parser_name="local_pymupdf",
        )

    job2 = db.get_job(job_id2, session_id="session_job_1")
    assert job2["status"] == "ready"
