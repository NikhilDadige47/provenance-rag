"""API package for Provenance RAG — Phase 5 & 6.

Public surface:
  - FastAPI `app` instance (src.api.main)
  - Session management (src.api.sessions)
  - Cost caps and rate limiting (src.api.caps)
  - Chat / usage / examples routers (src.api.chat)
  - Upload / jobs / lifecycle routers (src.api.upload)
  - Job runner and key manager (src.api.jobs)
  - Data lifecycle & deletion (src.api.lifecycle)
  - Privacy-safe logging helpers (src.api.logging)
  - Connection testing service (src.api.connections)
"""

from src.api.connections import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    verify_provider_connection,
)
from src.api.jobs import JobRunner
from src.api.lifecycle import delete_document, delete_session, purge_expired_sessions
from src.api.sessions import (
    CurrentSession,
    SessionCreateResponse,
    SessionState,
    VisitorLLMKeys,
    create_session,
    get_current_session,
)
from src.api.upload import router as upload_router
from src.api.upload_validation import UploadEstimateResponse, validate_pdf_upload

__all__ = [
    # connections (Phase 1 — re-exported)
    "ConnectionTestRequest",
    "ConnectionTestResponse",
    "verify_provider_connection",
    # sessions (Phase 5)
    "CurrentSession",
    "SessionCreateResponse",
    "SessionState",
    "VisitorLLMKeys",
    "create_session",
    "get_current_session",
    # upload & jobs (Phase 6)
    "JobRunner",
    "UploadEstimateResponse",
    "delete_document",
    "delete_session",
    "purge_expired_sessions",
    "upload_router",
    "validate_pdf_upload",
]
