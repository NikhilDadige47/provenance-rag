"""Upload and ingestion API endpoints.

Implements roadmap P6-T1 through P6-T6:
- POST   /upload/validate          — validate PDF, local page count & chunk estimate
- POST   /upload                   — submit PDF for asynchronous background ingestion
- GET    /jobs/{job_id}            — poll ingestion state & quality gate warnings
- GET    /session/documents        — list ingested documents for caller's session
- DELETE /session/documents/{doc_id} — delete a document and its vectors
- DELETE /session                  — immediate hard wipe of all session data
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from src.api.caps import (
    check_and_increment_daily_jobs,
    check_ip_daily_upload_limit,
    check_ip_rate_limit,
    check_kill_switch_uploads,
    client_ip_from_request,
    increment_ip_daily_uploads,
)
from src.api.connections import verify_provider_connection
from src.api.jobs import JobRunner
from src.api.lifecycle import delete_document, delete_session
from src.api.sessions import SessionState, get_current_session
from src.api.upload_validation import (
    MAX_UPLOAD_SIZE_BYTES,
    UploadEstimateResponse,
    build_upload_estimate,
    validate_pdf_upload,
)
from src.ingest.parsers.selection import (
    DEFAULT_UPLOAD_PARSER,
    UploadParserError,
    canonical_parser_label,
    normalize_upload_parser,
    visitor_parser_key_required,
)
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.security.secret import Secret
from src.storage.db import DatabaseManager

logger = logging.getLogger("provenance_rag.api.upload")

router = APIRouter(tags=["upload"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class JobResponse(BaseModel):
    """Job status response."""

    job_id: str
    session_id: str
    doc_id: str | None = None
    parser_name: str
    status: str = Field(
        description="Current state: queued, parsing, chunking, embedding, indexing, ready, failed"
    )
    pages: int = 0
    chunks: int = 0
    error_message: str | None = None
    quality_warnings: list[str] | None = None
    quality_advice: str | None = None
    parser_used: str | None = None
    degraded: bool = False
    started_at: str
    finished_at: str | None = None


class JobSubmitResponse(BaseModel):
    """Response returned when a background ingestion job is created."""

    job_id: str
    status: str
    filename: str
    page_count: int
    estimated_chunks: int
    parser_used: str
    message: str


class DocumentMetadataResponse(BaseModel):
    """Metadata for an ingested document."""

    doc_id: str
    session_id: str
    title: str
    page_count: int
    parser_used: str
    parser_version: str
    chunking_version: str
    embedding_version: str
    ingested_at: str
    quality_warnings: list[str] | None = None
    chunk_count: int = 0
    filename: str = ""
    degraded: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/upload/validate",
    response_model=UploadEstimateResponse,
    summary="Validate PDF and estimate chunk count",
    description=(
        "Pre-flight check: validates magic bytes, checks for encryption, counts pages locally "
        "via PyMuPDF ($0), and shows remaining session quota before any upload occurs."
    ),
)
@router.post(
    "/upload/estimate",
    response_model=UploadEstimateResponse,
    summary="Estimate chunk count and validate PDF (alias for /upload/validate)",
)
async def validate_and_estimate_upload(
    request: Request,
    file: UploadFile = File(..., description="PDF document to inspect"),
    parser: str = Form(
        DEFAULT_UPLOAD_PARSER,
        description="auto (owner waterfall), local_pymupdf, llamaparse, or landingai",
    ),
    parser_key: str | None = Form(None, description="Optional parser API key"),
    session: SessionState = Depends(get_current_session),
    x_parser_key: str | None = Header(None, alias="X-Parser-Key"),
) -> UploadEstimateResponse:
    """Validate PDF integrity and return cost/quota preview."""
    cfg: OwnerConfig = request.app.state.cfg
    db: DatabaseManager = request.app.state.db
    effective_parser_key = x_parser_key or parser_key

    # Read uploaded file bytes in memory
    file_bytes = await file.read()

    # Validate PDF
    validation = validate_pdf_upload(
        filename=file.filename or "document.pdf",
        file_bytes=file_bytes,
        session_id=session.session_id,
        db=db,
        cfg=cfg,
    )

    try:
        parser_clean = normalize_upload_parser(parser)
    except UploadParserError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    session_row = db.get_session(session.session_id) or {}
    estimate = build_upload_estimate(
        validation=validation,
        parser_name=parser_clean,
        session_row=session_row,
        cfg=cfg,
    )

    # If visitor provided a parser key for a parser they must fund, pre-flight test it
    if effective_parser_key and estimate.requires_visitor_key:
        test_res = await verify_provider_connection(
            provider=parser_clean, key=Secret(effective_parser_key)
        )
        if not test_res.ok:
            estimate.can_proceed = False
            estimate.message = f"Parser API key verification failed: {test_res.hint}"

    return estimate


@router.post(
    "/upload",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit PDF document for background ingestion",
    description=(
        "Validates PDF, creates a background ingestion job, and starts the processing pipeline. "
        "Default parser=auto uses owner Landing AI credits, then LlamaParse, then local PyMuPDF. "
        "A visitor parser key (if supplied for an explicit cloud parser) is held in memory "
        "for this job only and shredded upon completion."
    ),
)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="PDF file to ingest"),
    parser: str = Form(
        DEFAULT_UPLOAD_PARSER,
        description="auto (Landing AI → LlamaParse → local), local_pymupdf, llamaparse, or landingai",
    ),
    parser_key: str | None = Form(None, description="Optional parser API key from form"),
    allow_fallback: bool = Form(
        True, description="Automatically re-parse locally if cloud parser fails"
    ),
    terms_accepted: bool = Form(
        False,
        description="Visitor confirmed they have the right to upload and accept data routing",
    ),
    session: SessionState = Depends(get_current_session),
    x_parser_key: str | None = Header(None, alias="X-Parser-Key"),
) -> JobSubmitResponse:
    """Submit PDF for asynchronous background ingestion."""
    cfg: OwnerConfig = request.app.state.cfg
    db: DatabaseManager = request.app.state.db
    store: QdrantVectorStore = getattr(request.app.state, "store", None)
    if not store:
        store = QdrantVectorStore(cfg=cfg)
        request.app.state.store = store

    effective_parser_key = x_parser_key or parser_key

    # 1. Kill switch check
    check_kill_switch_uploads(cfg)

    # 2. Rate limit + daily upload cap (before reading a large body)
    client_ip = client_ip_from_request(request)
    check_ip_rate_limit(client_ip)
    check_ip_daily_upload_limit(db, client_ip)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            # Multipart overhead is small; reject obviously oversized bodies early.
            if int(content_length) > MAX_UPLOAD_SIZE_BYTES + (2 * 1024 * 1024):
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Upload exceeds the 10MB limit.",
                )
        except ValueError:
            pass

    if not terms_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must accept the upload terms before submitting a document.",
        )

    # 3. Read uploaded bytes
    file_bytes = await file.read()

    # 4. Validate PDF
    validation = validate_pdf_upload(
        filename=file.filename or "document.pdf",
        file_bytes=file_bytes,
        session_id=session.session_id,
        db=db,
        cfg=cfg,
    )

    # 5. Resolve parser. auto = owner-paid waterfall, never requires a visitor key.
    try:
        parser_clean = normalize_upload_parser(parser)
    except UploadParserError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if visitor_parser_key_required(parser_clean, cfg) and not effective_parser_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Parser '{parser_clean}' requires an API key. Pass it in the X-Parser-Key header, "
                "use parser=auto (owner-paid waterfall), or choose local_pymupdf."
            ),
        )

    runner: JobRunner = getattr(request.app.state, "job_runner", None)
    if not runner:
        runner = JobRunner(db=db, store=store, cfg=cfg)
        request.app.state.job_runner = runner
    if not runner.can_accept_job():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many documents are being processed. Please wait and retry.",
        )

    check_and_increment_daily_jobs(db, cfg)

    # 6. Create job in SQLite
    job_id = "job_" + uuid.uuid4().hex[:12]
    db.create_job(
        job_id=job_id,
        session_id=session.session_id,
        parser_name=parser_clean,
        status="queued",
    )

    increment_ip_daily_uploads(db, client_ip)

    # 8. Fire background task with a strong reference so it cannot be GC'd
    runner.spawn_ingestion_pipeline(
        job_id=job_id,
        session_id=session.session_id,
        filename=validation.filename,
        file_bytes=file_bytes,
        parser_name=parser_clean,
        parser_key=effective_parser_key,
        allow_fallback=allow_fallback,
        client_ip=client_ip,
    )

    return JobSubmitResponse(
        job_id=job_id,
        status="queued",
        filename=validation.filename,
        page_count=validation.page_count,
        estimated_chunks=validation.estimated_chunks,
        parser_used=parser_clean,
        message="Document submitted for background ingestion. Poll status at GET /jobs/{job_id}.",
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get ingestion job status",
    description="Poll progress of an active or completed background document ingestion job.",
)
async def get_job_status(
    job_id: str,
    request: Request,
    session: SessionState = Depends(get_current_session),
) -> JobResponse:
    """Fetch job progress, enforcing multi-tenant session isolation."""
    db: DatabaseManager = request.app.state.db

    # Multi-tenant isolation: strictly verify job belongs to caller's session
    job = db.get_job(job_id=job_id, session_id=session.session_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found in active session.",
        )

    # Parse quality flags if present
    quality_warnings: list[str] | None = None
    quality_advice: str | None = None
    if job.get("quality_flags"):
        try:
            q_data = json.loads(job["quality_flags"])
            quality_warnings = q_data.get("warnings")
            quality_advice = q_data.get("advice")
        except Exception:
            quality_warnings = [str(job["quality_flags"])]

    parser_used = None
    doc_id = job.get("doc_id")
    if doc_id:
        document = db.get_document(doc_id, session_id=session.session_id)
        if document:
            parser_used = canonical_parser_label(document.get("parser_used"))
    if not parser_used:
        parser_used = canonical_parser_label(job.get("parser_name"))
    degraded = parser_used == "local_pymupdf"

    return JobResponse(
        job_id=job["job_id"],
        session_id=job["session_id"],
        doc_id=job.get("doc_id"),
        parser_name=job["parser_name"],
        status=job["status"],
        pages=job.get("pages", 0) or 0,
        chunks=job.get("chunks", 0) or 0,
        error_message=job.get("error_message"),
        quality_warnings=quality_warnings,
        quality_advice=quality_advice,
        parser_used=parser_used,
        degraded=degraded,
        started_at=job["started_at"],
        finished_at=job.get("finished_at"),
    )


@router.get(
    "/session/documents",
    response_model=list[DocumentMetadataResponse],
    summary="List session documents",
    description="Returns all documents successfully ingested in the current session.",
)
async def list_session_documents(
    request: Request,
    session: SessionState = Depends(get_current_session),
) -> list[DocumentMetadataResponse]:
    """List documents belonging to the caller's session."""
    db: DatabaseManager = request.app.state.db
    docs = db.list_documents(session_id=session.session_id)

    results: list[DocumentMetadataResponse] = []
    for d in docs:
        quality_warnings: list[str] | None = None
        if d.get("quality_flags"):
            try:
                q_data = json.loads(d["quality_flags"])
                quality_warnings = q_data.get("warnings")
            except Exception:
                quality_warnings = None

        parser_used = canonical_parser_label(d.get("parser_used"))
        results.append(
            DocumentMetadataResponse(
                doc_id=d["doc_id"],
                session_id=d["session_id"],
                title=d["title"],
                page_count=d["page_count"],
                parser_used=parser_used,
                parser_version=d.get("parser_version", "1.0"),
                chunking_version=d.get("chunking_version", "hybrid-v1"),
                embedding_version=d.get("embedding_version", "emb-v1"),
                ingested_at=d["ingested_at"],
                quality_warnings=quality_warnings,
                chunk_count=int(d.get("chunk_count") or 0),
                filename=str(d.get("filename") or d.get("title") or "document.pdf"),
                degraded=parser_used == "local_pymupdf",
            )
        )
    return results


@router.delete(
    "/session/documents/{doc_id}",
    summary="Delete a single document",
    description="Deletes a document from the session along with all corresponding Qdrant vectors and SQL parents.",
)
async def delete_single_document(
    doc_id: str,
    request: Request,
    session: SessionState = Depends(get_current_session),
) -> dict[str, Any]:
    """Delete a document by ID within the current session."""
    db: DatabaseManager = request.app.state.db
    store: QdrantVectorStore = getattr(request.app.state, "store", None)
    if not store:
        store = QdrantVectorStore(cfg=request.app.state.cfg)

    result = delete_document(doc_id=doc_id, session_id=session.session_id, db=db, store=store)
    if result["status"] == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["message"],
        )
    return result


@router.delete(
    "/session",
    summary="Delete all session data (Delete my data)",
    description=(
        "Permanently wipes all vectors, parent chunks, documents, jobs, and session cache. "
        "Requires zero visitor keys."
    ),
)
async def delete_active_session(
    request: Request,
    response: Response,
    session: SessionState = Depends(get_current_session),
) -> dict[str, Any]:
    """Hard wipe of all data associated with caller's session."""
    db: DatabaseManager = request.app.state.db
    store: QdrantVectorStore = getattr(request.app.state, "store", None)
    if not store:
        store = QdrantVectorStore(cfg=request.app.state.cfg)

    result = delete_session(session_id=session.session_id, db=db, store=store)
    response.delete_cookie("session_token", path="/")
    return result


class SessionPurgePayload(BaseModel):
    session_id: str | None = None


@router.post(
    "/session/purge",
    summary="Purge session data on browser close or unload",
    description="Immediate hard-wipe of all vectors, parent chunks, documents, jobs, and metadata when browser tab closes or reloads.",
)
async def purge_session_on_unload(
    request: Request,
    payload: SessionPurgePayload | None = None,
) -> dict[str, Any]:
    """Beacon/unload endpoint to hard-wipe session vectors and metadata."""
    auth = request.headers.get("Authorization", "")
    token: str | None = None
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    elif payload and payload.session_id:
        token = payload.session_id.strip()

    # Fallback to body raw json if sent via navigator.sendBeacon
    if not token:
        try:
            body = await request.body()
            if body:
                data = json.loads(body.decode("utf-8"))
                token = data.get("session_id")
        except Exception:
            pass

    if not token:
        return {"status": "noop", "message": "No session token supplied."}

    db: DatabaseManager = request.app.state.db
    store: QdrantVectorStore = getattr(request.app.state, "store", None)
    if not store:
        store = QdrantVectorStore(cfg=request.app.state.cfg)

    return delete_session(session_id=token, db=db, store=store)
