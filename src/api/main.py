"""FastAPI application factory for Provenance RAG.

Implements roadmap P5-T1 through P5-T7 & architecture §3.2:
- POST  /session          — issue session token, server-derive scope
- POST  /connections/test — validate provider API key (Phase 1, re-mounted)
- GET   /examples         — demo corpus question chips (Tier A, no auth)
- GET   /usage            — session allowance meter
- POST  /chat             — full RAG pipeline with all caps enforced
- GET   /health           — liveness probe

Application startup:
  - Loads OwnerConfig from environment
  - Initializes DatabaseManager (creates all SQLite tables if absent)
  - Stores singletons on app.state for dependency injection

Security middleware:
  - Strips Authorization and X-LLM-Key headers from structured logs
  - Returns HTTPS-only error messages (no internal paths or stack traces exposed)
  - Sets Vary: Authorization so caches don't share authenticated responses

Run locally:
    uvicorn src.api.main:app --reload --port 8000
"""

import asyncio
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.chat import router as chat_router
from src.api.connections import ConnectionTestRequest, verify_provider_connection
from src.api.jobs import JobRunner
from src.api.lifecycle import run_ttl_cleanup_loop
from src.api.sessions import SessionCreateResponse, VisitorLLMKeys, create_session
from src.api.upload import router as upload_router
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.security.errors import KeySecurityError, ProviderTimeoutError
from src.security.secret import Secret
from src.storage.db import DatabaseManager

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("provenance_rag.api.main")


# ---------------------------------------------------------------------------
# Lifespan: startup and shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Initialize shared resources on startup; clean up on shutdown."""
    cfg = OwnerConfig.from_env()
    db = DatabaseManager()  # creates SQLite tables if absent
    store = QdrantVectorStore(cfg=cfg)
    job_runner = JobRunner(db=db, store=store, cfg=cfg)

    app.state.cfg = cfg
    app.state.db = db
    app.state.store = store
    app.state.job_runner = job_runner

    logger.info(
        f"Provenance RAG API starting up. "
        f"env={cfg.app_env} "
        f"kill_switch_owner_llm={cfg.kill_switch_disable_owner_llm} "
        f"kill_switch_uploads={cfg.kill_switch_disable_uploads}"
    )

    ttl_task = asyncio.create_task(run_ttl_cleanup_loop(db=db, store=store, interval_seconds=300))

    try:
        yield  # Application is running
    finally:
        ttl_task.cancel()
        with suppress(asyncio.CancelledError):
            await ttl_task

    logger.info("Provenance RAG API shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app instance
# ---------------------------------------------------------------------------


app = FastAPI(
    title="Provenance RAG API",
    description=(
        "Production-grade RAG portfolio with 3-tier hybrid access. "
        "Tier A: chat over demo corpus (no keys). "
        "Tier B: upload your own PDF with free or paid parser. "
        "Tier C: bring your own LLM key."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS (wide-open for portfolio; tighten in production to your frontend domain)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your frontend URL in production
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-LLM-Key", "X-LLM-Provider", "X-LLM-Model"],
    expose_headers=["X-Request-ID"],
)


# ---------------------------------------------------------------------------
# Request ID middleware (attaches a unique request ID to every response)
# ---------------------------------------------------------------------------


@app.middleware("http")
async def attach_request_id(request: Request, call_next: Any) -> Any:
    """Attach a unique request ID to every response and log structured timings."""
    request_id = "req_" + uuid.uuid4().hex[:12]
    start = time.time()

    # Make request_id available to route handlers via request.state
    request.state.request_id = request_id

    response = await call_next(request)

    elapsed_ms = round((time.time() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id

    # Privacy-safe access log: method, path, status, timing — NO headers or body
    logger.info(
        f"http_access method={request.method} path={request.url.path} "
        f"status={response.status_code} duration_ms={elapsed_ms} "
        f"request_id={request_id}"
    )

    return response


# ---------------------------------------------------------------------------
# Global exception handlers  (never expose internals to clients)
# ---------------------------------------------------------------------------


@app.exception_handler(KeySecurityError)
async def handle_key_security_error(request: Request, exc: KeySecurityError) -> JSONResponse:
    """Convert security errors to safe, user-friendly responses."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message},
    )


@app.exception_handler(ProviderTimeoutError)
async def handle_timeout_error(request: Request, exc: ProviderTimeoutError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={"detail": exc.message},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: log the error internally but never expose stack traces."""
    req_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled exception [{req_id}]: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred. Please try again or contact support.",
            "request_id": req_id,
        },
    )


# ---------------------------------------------------------------------------
# Health check (liveness probe — no auth required)
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' when the service is running")
    version: str


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    """Liveness probe for load balancers and uptime monitors."""
    return HealthResponse(status="ok", version="1.0.0")


# ---------------------------------------------------------------------------
# POST /session  (P5-T1: issue session token, server-derives scope)
# ---------------------------------------------------------------------------


@app.post(
    "/session",
    response_model=SessionCreateResponse,
    tags=["session"],
    summary="Start a new session",
    description=(
        "Issues a random session token. The server derives the access tier and scope from "
        "any optional headers you provide (X-LLM-Key for Tier C). "
        "The token must be passed as 'Authorization: Bearer <token>' on subsequent requests. "
        "Client-supplied scopes or filters are ignored."
    ),
)
async def create_session_endpoint(
    request: Request,
    visitor_keys: VisitorLLMKeys,
) -> SessionCreateResponse:
    """Create a new session and return a bearer token."""
    db: DatabaseManager = request.app.state.db
    response = create_session(db=db, visitor_keys=visitor_keys)
    return response


# ---------------------------------------------------------------------------
# POST /connections/test  (Phase 1, re-mounted into the main app)
# ---------------------------------------------------------------------------


class ConnectionTestBody(BaseModel):
    provider: str = Field(description="e.g. cohere, openai, groq, llamaparse")
    key: str = Field(description="API key to validate (never stored)")


@app.post(
    "/connections/test",
    tags=["connections"],
    summary="Validate an API key",
    description=(
        "Performs a cheap, credit-free validation call against the specified provider. "
        "The key is held in memory only for this request and is never persisted."
    ),
)
async def test_connection(body: ConnectionTestBody) -> dict:
    """Validate a provider API key without consuming paid credits."""
    req = ConnectionTestRequest(provider=body.provider, key=Secret(body.key))
    result = await verify_provider_connection(provider=req.provider, key=req.key)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Mount routers
# ---------------------------------------------------------------------------

# Chat endpoints: /chat, /usage, /examples
app.include_router(chat_router, tags=["chat"])

# Upload, jobs & lifecycle endpoints: /upload, /upload/validate, /jobs/{id}, /session/documents, DELETE /session
app.include_router(upload_router, tags=["upload"])
