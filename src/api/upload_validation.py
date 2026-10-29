"""Upload validation, magic byte inspection, and cost estimation service.

Implements roadmap P6-T1 and P6-T2:
- Magic-byte validation (%PDF-) and extension check
- File size bounds (default max 10MB)
- Encrypted/password-protected PDF rejection
- Local page count via PyMuPDF in memory ($0 cost)
- Session quota enforcement (max docs, max pages)
- Chunk count estimation for user transparency
"""

from __future__ import annotations

import hashlib
from typing import Any

import pymupdf
from fastapi import HTTPException, status
from pydantic import BaseModel

from src.ingest.parsers.selection import visitor_parser_key_required
from src.security.config import OwnerConfig
from src.security.credit_config import VISITOR_ALLOWANCE
from src.storage.db import DatabaseManager

# ---------------------------------------------------------------------------
# Constants & Defaults
# ---------------------------------------------------------------------------

PDF_MAGIC_BYTES = b"%PDF-"
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_PAGES_PER_DOC = 30
DEFAULT_MAX_DOCS_PER_SESSION = 3
DEFAULT_MAX_TOTAL_PAGES_PER_SESSION = 30
ESTIMATED_CHUNKS_PER_PAGE = 20


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    """Result of PDF validation and inspection."""

    filename: str
    content_hash: str
    file_size_bytes: int
    page_count: int
    estimated_chunks: int
    title: str


class UploadEstimateResponse(BaseModel):
    """Estimate and session quota preview for visitor confirmation."""

    filename: str
    page_count: int
    estimated_chunks: int
    requires_visitor_key: bool
    parser_name: str
    session_docs_count: int
    session_max_docs: int
    session_pages_used: int
    session_max_pages: int
    session_chunks_embedded: int
    session_max_chunks: int
    can_proceed: bool
    message: str | None = None


# ---------------------------------------------------------------------------
# Validation Functions
# ---------------------------------------------------------------------------


def validate_pdf_upload(
    filename: str,
    file_bytes: bytes,
    session_id: str,
    db: DatabaseManager,
    cfg: OwnerConfig,
) -> ValidationResult:
    """Validate PDF upload for file integrity, encryption, size, and session caps.

    Raises:
        HTTPException with status 400 or 413 on any validation failure.
    """
    # 1. File extension check
    clean_filename = (filename or "document.pdf").strip()
    if not clean_filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension: '{clean_filename}'. Only PDF files are supported.",
        )

    # 2. File size check
    file_size = len(file_bytes)
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded PDF file is empty (0 bytes).",
        )
    if file_size > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {max_mb} MB (received {file_size / (1024 * 1024):.1f} MB).",
        )

    # 3. Magic-bytes check (%PDF-)
    if not file_bytes.startswith(PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file signature: Content does not start with PDF magic bytes (%PDF-).",
        )

    # 4. Open with PyMuPDF in memory to inspect structure and encryption
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed or corrupted PDF file: {exc}",
        ) from exc

    try:
        # Check password protection / encryption
        if doc.is_encrypted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This PDF is password-protected or encrypted. Please remove encryption before uploading.",
            )

        page_count = len(doc)
        if page_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded PDF contains no readable pages.",
            )

        # Max pages per document check
        max_pages_per_doc = cfg.session_max_total_pages or VISITOR_ALLOWANCE["max_pages_doc"]
        if page_count > max_pages_per_doc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Document has {page_count} pages, which exceeds the limit of "
                    f"{max_pages_per_doc} pages per document."
                ),
            )

        # Extract title from metadata or fallback to clean filename
        meta_title = (doc.metadata or {}).get("title", "").strip() if doc.metadata else ""
        title = meta_title if meta_title else clean_filename.rsplit(".", 1)[0].replace("_", " ")

    finally:
        doc.close()

    # 5. Session quota validation against SQLite counters
    session_row = db.get_session(session_id)
    if not session_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found. Please create a session first via POST /session.",
        )

    current_docs = session_row.get("docs_count", 0) or 0
    current_pages = session_row.get("pages_used", 0) or 0
    max_docs_session = cfg.session_max_documents
    max_pages_session = cfg.session_max_total_pages

    if current_docs + 1 > max_docs_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Session document limit reached ({current_docs}/{max_docs_session}). "
                "Delete existing documents or start a new session."
            ),
        )

    if current_pages + page_count > max_pages_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Uploading {page_count} pages would exceed your session allowance of "
                f"{max_pages_session} total pages (already used: {current_pages})."
            ),
        )

    content_hash = hashlib.sha256(file_bytes).hexdigest()
    estimated_chunks = max(1, page_count * ESTIMATED_CHUNKS_PER_PAGE)

    return ValidationResult(
        filename=clean_filename,
        content_hash=content_hash,
        file_size_bytes=file_size,
        page_count=page_count,
        estimated_chunks=estimated_chunks,
        title=title,
    )


def build_upload_estimate(
    validation: ValidationResult,
    parser_name: str,
    session_row: dict[str, Any],
    cfg: OwnerConfig,
) -> UploadEstimateResponse:
    """Build user-facing upload estimate and quota preview."""
    requires_key = visitor_parser_key_required(parser_name, cfg)
    current_docs = session_row.get("docs_count", 0) or 0
    current_pages = session_row.get("pages_used", 0) or 0
    current_chunks = session_row.get("chunks_embedded", 0) or 0

    max_docs = cfg.session_max_documents
    max_pages = cfg.session_max_total_pages
    max_chunks = cfg.session_max_chunks_embedded

    can_proceed = (
        (current_docs + 1 <= max_docs)
        and (current_pages + validation.page_count <= max_pages)
        and (current_chunks + validation.estimated_chunks <= max_chunks)
    )

    return UploadEstimateResponse(
        filename=validation.filename,
        page_count=validation.page_count,
        estimated_chunks=validation.estimated_chunks,
        requires_visitor_key=requires_key,
        parser_name=parser_name,
        session_docs_count=current_docs,
        session_max_docs=max_docs,
        session_pages_used=current_pages,
        session_max_pages=max_pages,
        session_chunks_embedded=current_chunks,
        session_max_chunks=max_chunks,
        can_proceed=can_proceed,
        message="Ready to upload." if can_proceed else "Session allowance exceeded.",
    )
