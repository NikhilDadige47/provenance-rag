"""Tests for upload validation, PDF integrity, encryption, size, and quota bounds (P6-T1, P6-T2)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from fastapi import HTTPException

from src.api.upload_validation import (
    MAX_UPLOAD_SIZE_BYTES,
    build_upload_estimate,
    validate_pdf_upload,
)
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager


def create_test_pdf_bytes(num_pages: int = 1, title: str = "Test Doc") -> bytes:
    """Helper to generate valid in-memory PDF bytes."""
    doc = pymupdf.open()
    doc.set_metadata({"title": title})
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((50, 70), f"Section {i + 1}", fontsize=16)
        page.insert_text((50, 100), f"This is page content for page number {i + 1}.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def create_encrypted_pdf_bytes() -> bytes:
    """Helper to generate an encrypted/password-protected PDF."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), "Confidential data")
    data = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner_pass",
        user_pw="user_pass",
    )
    doc.close()
    return data


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    """Create a temporary test database."""
    db_file = tmp_path / "test_rag.db"
    db = DatabaseManager(db_path=db_file)
    db.create_or_get_session("session_val_1", tier="tier_b")
    return db


@pytest.fixture
def owner_cfg() -> OwnerConfig:
    return OwnerConfig(
        cohere_api_key="test_cohere",
        groq_api_key="test_groq",
        qdrant_url=":memory:",
    )


def test_validate_pdf_valid(test_db: DatabaseManager, owner_cfg: OwnerConfig) -> None:
    """Valid 2-page PDF passes validation cleanly."""
    pdf_bytes = create_test_pdf_bytes(num_pages=2, title="Financial Report")
    res = validate_pdf_upload(
        filename="report.pdf",
        file_bytes=pdf_bytes,
        session_id="session_val_1",
        db=test_db,
        cfg=owner_cfg,
    )
    assert res.filename == "report.pdf"
    assert res.page_count == 2
    assert res.estimated_chunks == 40
    assert res.title == "Financial Report"
    assert len(res.content_hash) == 64


def test_validate_rejects_non_pdf_extension(
    test_db: DatabaseManager, owner_cfg: OwnerConfig
) -> None:
    """Reject non-.pdf extension."""
    with pytest.raises(HTTPException) as exc:
        validate_pdf_upload(
            filename="malware.exe",
            file_bytes=b"fake content",
            session_id="session_val_1",
            db=test_db,
            cfg=owner_cfg,
        )
    assert exc.value.status_code == 400
    assert "Invalid file extension" in exc.value.detail


def test_validate_rejects_empty_file(test_db: DatabaseManager, owner_cfg: OwnerConfig) -> None:
    """Reject 0-byte file."""
    with pytest.raises(HTTPException) as exc:
        validate_pdf_upload(
            filename="empty.pdf",
            file_bytes=b"",
            session_id="session_val_1",
            db=test_db,
            cfg=owner_cfg,
        )
    assert exc.value.status_code == 400
    assert "empty" in exc.value.detail.lower()


def test_validate_rejects_oversized_file(test_db: DatabaseManager, owner_cfg: OwnerConfig) -> None:
    """Reject files larger than 10MB."""
    oversized_bytes = b"%PDF-" + b"0" * (MAX_UPLOAD_SIZE_BYTES + 100)
    with pytest.raises(HTTPException) as exc:
        validate_pdf_upload(
            filename="large.pdf",
            file_bytes=oversized_bytes,
            session_id="session_val_1",
            db=test_db,
            cfg=owner_cfg,
        )
    assert exc.value.status_code == 413
    assert "exceeds maximum allowed size" in exc.value.detail


def test_validate_rejects_fake_magic_bytes(
    test_db: DatabaseManager, owner_cfg: OwnerConfig
) -> None:
    """Reject files without %PDF- magic bytes."""
    with pytest.raises(HTTPException) as exc:
        validate_pdf_upload(
            filename="fake.pdf",
            file_bytes=b"<html><body>Not a PDF</body></html>",
            session_id="session_val_1",
            db=test_db,
            cfg=owner_cfg,
        )
    assert exc.value.status_code == 400
    assert "magic bytes" in exc.value.detail


def test_validate_rejects_encrypted_pdf(test_db: DatabaseManager, owner_cfg: OwnerConfig) -> None:
    """Reject encrypted/password-protected PDFs with user-friendly message."""
    enc_bytes = create_encrypted_pdf_bytes()
    with pytest.raises(HTTPException) as exc:
        validate_pdf_upload(
            filename="locked.pdf",
            file_bytes=enc_bytes,
            session_id="session_val_1",
            db=test_db,
            cfg=owner_cfg,
        )
    assert exc.value.status_code == 400
    assert "password-protected or encrypted" in exc.value.detail


def test_validate_rejects_excessive_pages_per_doc(
    test_db: DatabaseManager, owner_cfg: OwnerConfig
) -> None:
    """Reject document exceeding 30 pages."""
    pdf_bytes = create_test_pdf_bytes(num_pages=35)
    with pytest.raises(HTTPException) as exc:
        validate_pdf_upload(
            filename="long.pdf",
            file_bytes=pdf_bytes,
            session_id="session_val_1",
            db=test_db,
            cfg=owner_cfg,
        )
    assert exc.value.status_code == 400
    assert "exceeds the limit of 30 pages" in exc.value.detail


def test_validate_rejects_exceeded_session_docs(
    test_db: DatabaseManager, owner_cfg: OwnerConfig
) -> None:
    """Reject upload if session already has 3 documents."""
    # Populate 3 docs in session
    with test_db._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE sessions SET docs_count = 3 WHERE session_id = 'session_val_1'"
        )
        conn.commit()

    pdf_bytes = create_test_pdf_bytes(num_pages=1)
    with pytest.raises(HTTPException) as exc:
        validate_pdf_upload(
            filename="doc4.pdf",
            file_bytes=pdf_bytes,
            session_id="session_val_1",
            db=test_db,
            cfg=owner_cfg,
        )
    assert exc.value.status_code == 400
    assert "Session document limit reached" in exc.value.detail


def test_validate_rejects_exceeded_session_pages(
    test_db: DatabaseManager, owner_cfg: OwnerConfig
) -> None:
    """Reject upload if adding pages exceeds session max of 30 total pages."""
    # Set 28 pages already used
    with test_db._get_connection() as conn:
        conn.cursor().execute(
            "UPDATE sessions SET pages_used = 28 WHERE session_id = 'session_val_1'"
        )
        conn.commit()

    pdf_bytes = create_test_pdf_bytes(num_pages=5)  # 28 + 5 = 33 > 30
    with pytest.raises(HTTPException) as exc:
        validate_pdf_upload(
            filename="doc_pages.pdf",
            file_bytes=pdf_bytes,
            session_id="session_val_1",
            db=test_db,
            cfg=owner_cfg,
        )
    assert exc.value.status_code == 400
    assert "exceed your session allowance of 30 total pages" in exc.value.detail


def test_build_upload_estimate(test_db: DatabaseManager, owner_cfg: OwnerConfig) -> None:
    """Verify estimate builder calculation and key requirement detection."""
    pdf_bytes = create_test_pdf_bytes(num_pages=3)
    val = validate_pdf_upload(
        filename="estimate_test.pdf",
        file_bytes=pdf_bytes,
        session_id="session_val_1",
        db=test_db,
        cfg=owner_cfg,
    )
    s_row = test_db.get_session("session_val_1") or {}

    # Local parser: requires_key is False
    est_local = build_upload_estimate(val, "local_pymupdf", s_row, owner_cfg)
    assert est_local.requires_visitor_key is False
    assert est_local.page_count == 3
    assert est_local.can_proceed is True

    # LlamaParse: requires_key is True
    est_lp = build_upload_estimate(val, "llamaparse", s_row, owner_cfg)
    assert est_lp.requires_visitor_key is True
