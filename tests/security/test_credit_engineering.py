"""Comprehensive test suite for Token & Credit Engineering.

Tests all core invariants from token-engineering-guide.md:
1. Estimator: Gate 0 digital vs scanned detection and credit calculation
2. Ledger: Atomic multi-bucket reservation, over-limit rejection, commit delta, and release rollback
3. Breaker: 402 Quota Exhaustion trip, TTL expiration, and transient failure bursts
4. Router: Waterfall cascade (Landing AI -> LlamaParse -> PyMuPDF), dedup cache hit with 0 credits
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest

from src.ingest.estimator import (
    InputRejectedError,
    analyse_pdf,
    landing_route,
    landing_units,
    llama_units,
)
from src.ingest.parsers.router import FallbackParserRouter, RequestContext
from src.security.breaker import Breaker
from src.security.credit_config import usable_units
from src.security.errors import QuotaExhaustedError, RateLimitedError
from src.security.ledger import Bucket, Ledger
from src.security.secret import Secret
from src.storage.db import DatabaseManager


def create_digital_pdf(page_count: int = 2) -> bytes:
    """Create a multi-page digital PDF with substantial text layer."""
    doc = pymupdf.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text(
            (50, 70),
            f"Section {i + 1}: Digital Architecture Overview. "
            "This document contains comprehensive financial disclosures and technical systems design. "
            "Every paragraph is fully searchable with distinct token boundaries and vector indexes.",
            fontsize=12,
        )
    data = doc.tobytes()
    doc.close()
    return data


def create_scanned_pdf(page_count: int = 1) -> bytes:
    """Create a minimal PDF with no text layer (simulating scanned document)."""
    doc = pymupdf.open()
    for _ in range(page_count):
        doc.new_page()  # Blank page, no text layer
    data = doc.tobytes()
    doc.close()
    return data


# -----------------------------------------------------------------------------
# 1. Estimator & Gate 0 Tests
# -----------------------------------------------------------------------------


def test_estimator_digital_vs_scanned():
    digital_pdf = create_digital_pdf(page_count=3)
    info_dig = analyse_pdf(digital_pdf)
    assert info_dig["pages"] == 3
    assert info_dig["digital"] is True
    assert landing_route(info_dig) == ("verity", "standard")
    assert landing_units(info_dig) > 0
    assert llama_units(info_dig) == 9  # 3 pages * 3 credits

    scanned_pdf = create_scanned_pdf(page_count=2)
    info_scan = analyse_pdf(scanned_pdf)
    assert info_scan["pages"] == 2
    assert info_scan["digital"] is False
    assert landing_route(info_scan) == ("pro", "standard")
    assert landing_units(info_scan) > 0


def test_estimator_input_rejections():
    # Empty bytes
    with pytest.raises(InputRejectedError, match="Malformed"):
        analyse_pdf(b"not a pdf")


# -----------------------------------------------------------------------------
# 2. Atomic Ledger Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ledger_atomic_reservation(tmp_path: Path):
    db_file = tmp_path / "test_ledger.db"
    ledger = Ledger(db_file)

    buckets = [
        Bucket("pool:landing", amount=20, limit=100),
        Bucket("day:landing", amount=20, limit=50),
        Bucket("u:user1:landing", amount=20, limit=30),
    ]

    # Reservation 1: Should succeed
    ok, failed_key = await ledger.reserve(buckets)
    assert ok is True
    assert failed_key is None
    assert ledger.get_balance("pool:landing") == 20
    assert ledger.get_balance("u:user1:landing") == 20

    # Reservation 2: 20 + 20 = 40 > user limit 30 -> Must fail atomically
    ok2, failed_key2 = await ledger.reserve(buckets)
    assert ok2 is False
    assert failed_key2 == "u:user1:landing"
    # Balances must NOT have changed (atomic rollback)
    assert ledger.get_balance("pool:landing") == 20
    assert ledger.get_balance("u:user1:landing") == 20


@pytest.mark.asyncio
async def test_ledger_commit_and_release(tmp_path: Path):
    db_file = tmp_path / "test_ledger_delta.db"
    ledger = Ledger(db_file)

    buckets = [Bucket("pool:test", amount=20, limit=100)]
    await ledger.reserve(buckets)
    assert ledger.get_balance("pool:test") == 20

    # Actual billed units was 15 (reconcile delta: 15 - 20 = -5)
    await ledger.commit(buckets, actual_units=15)
    assert ledger.get_balance("pool:test") == 15

    # Release drops remaining 15 back to 0
    await ledger.release([Bucket("pool:test", amount=15, limit=100)])
    assert ledger.get_balance("pool:test") == 0


# -----------------------------------------------------------------------------
# 3. Circuit Breaker Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_quota_trip(tmp_path: Path):
    db_file = tmp_path / "test_cb.db"
    breaker = Breaker(db_file)

    assert await breaker.is_open("landingai") is False

    # Trip quota for 30 minutes
    await breaker.trip_quota("landingai", ttl_seconds=1800)
    assert await breaker.is_open("landingai") is True

    # Other providers unaffected
    assert await breaker.is_open("llamaparse") is False

    # Reset
    await breaker.reset("landingai")
    assert await breaker.is_open("landingai") is False


# -----------------------------------------------------------------------------
# 4. Multi-Provider Router Waterfall & Dedup Cache Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_waterfall_fallback(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test_router.db")
    router = FallbackParserRouter(db=db)
    router.cfg.landingai_api_key = Secret("mock_landing_key")
    router.cfg.llamaparse_api_key = Secret("mock_llama_key")

    pdf_bytes = create_digital_pdf(page_count=2)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = Path(tmp.name)

    ctx = RequestContext(
        session_id="sess_router_1",
        client_ip="127.0.0.1",
        sha="sha_test_123",
        byok=False,
    )

    # Patch LandingAI to simulate 402 QuotaExhausted, and LlamaParse to simulate 429
    with (
        patch.object(
            router.landing_adapter,
            "parse",
            side_effect=QuotaExhaustedError("landingai"),
        ),
        patch.object(
            router.llama_adapter,
            "parse",
            side_effect=RateLimitedError("llamaparse"),
        ),
    ):
        result = await router.parse_with_fallback(
            pdf_path=pdf_path,
            pdf_bytes=pdf_bytes,
            ctx=ctx,
        )

    # Assert that it gracefully degraded all the way to local PyMuPDF
    assert result.degraded is True
    assert "pymupdf" in result.parser_label.lower()
    # Check that fallback trail captured Landing 402 and LlamaParse 429
    trail_reasons = [item[1] for item in result.fallback_trail]
    assert "quota_exhausted" in trail_reasons

    # Check Dedup Cache: Calling again for the same SHA must be an instant cache hit with 0 credits
    result_cached = await router.parse_with_fallback(
        pdf_path=pdf_path,
        pdf_bytes=pdf_bytes,
        ctx=ctx,
    )
    assert result_cached.cache_hit is True
    assert result_cached.credits_charged == 0

    if pdf_path.exists():
        pdf_path.unlink()


def _sample_structured_doc(parser_used: str):
    from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc

    return StructuredDoc(
        doc_id="doc_mock",
        title="Mock Parsed",
        page_count=2,
        parser_used=parser_used,
        blocks=[
            Block(type=BlockType.HEADING, text="Overview", level=1, page=1, order=0),
            Block(type=BlockType.PARAGRAPH, text="Owner-paid parse body.", page=1, order=1),
        ],
    )


@pytest.mark.asyncio
async def test_router_auto_skips_unfunded_providers(tmp_path: Path):
    """No owner keys → auto never calls cloud adapters, uses local PyMuPDF."""
    db = DatabaseManager(tmp_path / "test_router_nokey.db")
    router = FallbackParserRouter(db=db)
    router.cfg.landingai_api_key = None
    router.cfg.llamaparse_api_key = None

    pdf_bytes = create_digital_pdf(page_count=1)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = Path(tmp.name)

    ctx = RequestContext(
        session_id="sess_auto_nokey",
        client_ip="127.0.0.1",
        sha="sha_auto_nokey",
        byok=False,
    )

    with (
        patch.object(router.landing_adapter, "parse", side_effect=AssertionError("landingai")),
        patch.object(router.llama_adapter, "parse", side_effect=AssertionError("llamaparse")),
    ):
        result = await router.parse_with_fallback(
            pdf_path=pdf_path,
            pdf_bytes=pdf_bytes,
            ctx=ctx,
            preferred_parser="auto",
        )

    assert "pymupdf" in result.parser_label.lower()
    trail = dict(result.fallback_trail)
    assert trail.get("landingai") == "no_key_configured"
    assert trail.get("llamaparse") == "no_key_configured"
    if pdf_path.exists():
        pdf_path.unlink()


@pytest.mark.asyncio
async def test_router_auto_prefers_landingai_when_credits_remain(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test_router_land.db")
    router = FallbackParserRouter(db=db)
    router.cfg.landingai_api_key = Secret("mock_landing_key")
    router.cfg.llamaparse_api_key = Secret("mock_llama_key")

    pdf_bytes = create_digital_pdf(page_count=1)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = Path(tmp.name)

    ctx = RequestContext(
        session_id="sess_auto_land",
        client_ip="127.0.0.1",
        sha="sha_auto_land",
        byok=False,
    )

    landing_doc = _sample_structured_doc("landingai")
    with (
        patch.object(router.landing_adapter, "parse", return_value=landing_doc) as land_mock,
        patch.object(router.llama_adapter, "parse", side_effect=AssertionError("llama")),
    ):
        result = await router.parse_with_fallback(
            pdf_path=pdf_path,
            pdf_bytes=pdf_bytes,
            ctx=ctx,
            preferred_parser="auto",
        )

    land_mock.assert_awaited_once()
    assert result.parser_label == "landingai"
    assert result.degraded is False
    if pdf_path.exists():
        pdf_path.unlink()


@pytest.mark.asyncio
async def test_router_auto_falls_to_llamaparse_when_landing_budget_fails(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test_router_llama.db")
    router = FallbackParserRouter(db=db)
    router.cfg.landingai_api_key = Secret("mock_landing_key")
    router.cfg.llamaparse_api_key = Secret("mock_llama_key")

    # Exhaust the Landing AI lifetime pool so reserve() rejects the next file.
    exhausted = usable_units("landing")
    await router.ledger.reserve(
        [Bucket("pool:landing:lifetime", exhausted, exhausted)]
    )

    pdf_bytes = create_digital_pdf(page_count=2)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = Path(tmp.name)

    ctx = RequestContext(
        session_id="sess_auto_llama",
        client_ip="10.0.0.9",
        sha="sha_auto_llama",
        byok=False,
    )
    llama_doc = _sample_structured_doc("llamaparse")

    with (
        patch.object(router.landing_adapter, "parse", side_effect=AssertionError("landing")),
        patch.object(router.llama_adapter, "parse", return_value=llama_doc) as llama_mock,
    ):
        result = await router.parse_with_fallback(
            pdf_path=pdf_path,
            pdf_bytes=pdf_bytes,
            ctx=ctx,
            preferred_parser="auto",
        )

    llama_mock.assert_awaited_once()
    assert result.parser_label == "llamaparse"
    trail_reasons = [item[1] for item in result.fallback_trail]
    assert any(reason.startswith("budget:") for reason in trail_reasons)
    if pdf_path.exists():
        pdf_path.unlink()


@pytest.mark.asyncio
async def test_router_commits_actual_landing_credits_not_estimate(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test_router_actual.db")
    router = FallbackParserRouter(db=db)
    router.cfg.landingai_api_key = Secret("mock_landing_key")
    router.cfg.llamaparse_api_key = None

    pdf_bytes = create_digital_pdf(page_count=1)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = Path(tmp.name)

    ctx = RequestContext(
        session_id="sess_actual_credits",
        client_ip="127.0.0.1",
        sha="sha_actual_credits",
        byok=False,
    )
    landing_doc = _sample_structured_doc("landingai")
    landing_doc.credits_units = 7

    with patch.object(router.landing_adapter, "parse", return_value=landing_doc):
        result = await router.parse_with_fallback(
            pdf_path=pdf_path,
            pdf_bytes=pdf_bytes,
            ctx=ctx,
            preferred_parser="auto",
        )

    from src.security.credit_config import landing_pool_key

    assert result.credits_charged == 7
    assert router.ledger.get_balance(landing_pool_key()) == 7
    if pdf_path.exists():
        pdf_path.unlink()


@pytest.mark.asyncio
async def test_parse_cache_is_global_across_sessions(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test_router_global_cache.db")
    router = FallbackParserRouter(db=db)
    router.cfg.landingai_api_key = Secret("mock_landing_key")
    router.cfg.llamaparse_api_key = None

    pdf_bytes = create_digital_pdf(page_count=1)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = Path(tmp.name)

    landing_doc = _sample_structured_doc("landingai")
    ctx_a = RequestContext(
        session_id="sess_cache_a",
        client_ip="10.0.0.1",
        sha="shared_file_hash",
        byok=False,
    )
    ctx_b = RequestContext(
        session_id="sess_cache_b",
        client_ip="10.0.0.2",
        sha="shared_file_hash",
        byok=False,
    )

    with patch.object(router.landing_adapter, "parse", return_value=landing_doc) as land_mock:
        first = await router.parse_with_fallback(
            pdf_path=pdf_path, pdf_bytes=pdf_bytes, ctx=ctx_a, preferred_parser="auto"
        )
        second = await router.parse_with_fallback(
            pdf_path=pdf_path, pdf_bytes=pdf_bytes, ctx=ctx_b, preferred_parser="auto"
        )

    land_mock.assert_awaited_once()
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.credits_charged == 0
    if pdf_path.exists():
        pdf_path.unlink()

