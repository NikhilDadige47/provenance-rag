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
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api.chat import router as chat_router
from src.api.connections import ConnectionTestRequest, verify_provider_connection
from src.api.jobs import JobRunner
from src.api.lifecycle import run_ttl_cleanup_loop
from src.api.observability import record_request
from src.api.observability import snapshot as metrics_snapshot
from src.api.sessions import SessionCreateResponse, VisitorLLMKeys, create_session, resume_session
from src.api.upload import router as upload_router
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.security.errors import (
    InvalidKeyError,
    KeySecurityError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.security.ledger import Ledger
from src.security.secret import Secret
from src.storage.db import DatabaseManager, resolve_default_db_path

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
    db = DatabaseManager(
        db_path=resolve_default_db_path(data_dir=cfg.data_dir, sqlite_path=cfg.sqlite_path)
    )
    ledger = Ledger(db.db_path)
    store = QdrantVectorStore(cfg=cfg)
    job_runner = JobRunner(db=db, store=store, cfg=cfg)

    app.state.cfg = cfg
    app.state.db = db
    app.state.ledger = ledger
    app.state.store = store
    app.state.job_runner = job_runner

    try:
        interrupted = job_runner.fail_interrupted_jobs()
    except Exception:
        logger.exception("Could not mark interrupted ingest jobs failed")
        interrupted = 0

    logger.info(
        f"Provenance RAG API starting up. "
        f"env={cfg.app_env} "
        f"kill_switch_owner_llm={cfg.kill_switch_disable_owner_llm} "
        f"kill_switch_uploads={cfg.kill_switch_disable_uploads}"
    )
    if interrupted:
        logger.warning("Marked %s interrupted ingest job(s) failed after restart", interrupted)

    ttl_task = asyncio.create_task(run_ttl_cleanup_loop(db=db, store=store, interval_seconds=300))

    try:
        yield  # Application is running
    finally:
        ttl_task.cancel()
        ingest_tasks = list(job_runner._tasks)
        for task in ingest_tasks:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await ttl_task
        if ingest_tasks:
            await asyncio.gather(*ingest_tasks, return_exceptions=True)

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


_DEV_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)


def _cors_origins() -> list[str]:
    """Lock CORS to concrete origins. Wildcard + credentials is rejected by browsers."""
    try:
        cfg = OwnerConfig.from_env()
    except Exception:
        return list(_DEV_CORS_ORIGINS)
    if cfg.app_env.lower() == "production":
        origin = (cfg.frontend_origin or "").strip()
        return [origin] if origin else ["http://localhost:5173"]
    raw = (cfg.cors_origins or "*").strip()
    if raw == "*":
        origins = list(_DEV_CORS_ORIGINS)
        extra = (cfg.frontend_origin or "").strip()
        if extra and extra not in origins:
            origins.append(extra)
        return origins
    return [part.strip() for part in raw.split(",") if part.strip()] or list(_DEV_CORS_ORIGINS)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-LLM-Key",
        "X-LLM-Provider",
        "X-LLM-Model",
        "X-Parser-Key",
    ],
    expose_headers=["X-Request-ID"],
)


# ---------------------------------------------------------------------------
# Request ID middleware (attaches a unique request ID to every response)
# ---------------------------------------------------------------------------


def _request_is_https(request: Request) -> bool:
    """Honor X-Forwarded-Proto from the TLS terminator; otherwise use the URL scheme."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if forwarded:
        return forwarded == "https"
    return request.url.scheme == "https"


def _reject_insecure_production(request: Request) -> JSONResponse | None:
    """Block non-TLS traffic in production. /health stays reachable for internal probes."""
    cfg = getattr(request.app.state, "cfg", None)
    env = (getattr(cfg, "app_env", "development") or "development").lower()
    if env != "production":
        return None
    if request.url.path == "/health":
        return None
    if _request_is_https(request):
        return None
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": "HTTPS is required."},
    )


@app.middleware("http")
async def attach_request_id(request: Request, call_next: Any) -> Any:
    """Attach a unique request ID to every response and log structured timings."""
    request_id = "req_" + uuid.uuid4().hex[:12]
    start = time.time()

    # Make request_id available to route handlers via request.state
    request.state.request_id = request_id

    https_block = _reject_insecure_production(request)
    if https_block is not None:
        https_block.headers["X-Request-ID"] = request_id
        _apply_security_headers(request, https_block)
        record_request(https_block.status_code, round((time.time() - start) * 1000, 1))
        return https_block

    response = await call_next(request)

    elapsed_ms = round((time.time() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    _apply_security_headers(request, response)
    record_request(response.status_code, elapsed_ms)

    # Privacy-safe access log: method, path, status, timing — NO headers or body
    logger.info(
        f"http_access method={request.method} path={request.url.path} "
        f"status={response.status_code} duration_ms={elapsed_ms} "
        f"request_id={request_id}"
    )

    return response


def _apply_security_headers(request: Request, response: Any) -> None:
    """HSTS, CSP, and clickjacking headers. Docs UI keeps a looser CSP."""
    cfg = getattr(request.app.state, "cfg", None)
    env = (getattr(cfg, "app_env", "development") or "development").lower()
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if env == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
    path = request.url.path
    is_embeddable_pdf = path.startswith("/demo_corpus/") and path.lower().endswith(".pdf")
    if is_embeddable_pdf:
        # Same-origin iframe preview of the demo filings. The rest of the app stays unframable.
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'self'"
        return
    response.headers["X-Frame-Options"] = "DENY"
    if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi"):
        csp = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"
    else:
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "frame-src 'self' blob:; "
            "object-src 'self' blob:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
    response.headers["Content-Security-Policy"] = csp


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


@app.exception_handler(InvalidKeyError)
async def handle_invalid_key(request: Request, exc: InvalidKeyError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": exc.message})


@app.exception_handler(QuotaExhaustedError)
async def handle_quota_exhausted(request: Request, exc: QuotaExhaustedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED, content={"detail": exc.message}
    )


@app.exception_handler(RateLimitedError)
async def handle_rate_limited(request: Request, exc: RateLimitedError) -> JSONResponse:
    headers = {}
    if exc.retry_after_seconds:
        headers["Retry-After"] = str(int(exc.retry_after_seconds))
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": exc.message},
        headers=headers,
    )


@app.exception_handler(ProviderUnavailableError)
async def handle_provider_unavailable(
    request: Request, exc: ProviderUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": exc.message}
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
    status: str = Field(description="'ok' when the process is serving traffic")
    version: str
    ready: bool = True
    components: dict[str, str] = Field(default_factory=dict)


@app.get("/health", response_model=None, tags=["system"])
async def health_check(request: Request) -> HealthResponse | JSONResponse:
    """Liveness + readiness probe for load balancers and uptime monitors."""
    components: dict[str, str] = {}
    ready = True
    db: DatabaseManager | None = getattr(request.app.state, "db", None)
    store: QdrantVectorStore | None = getattr(request.app.state, "store", None)
    try:
        if db is not None:
            with db._get_connection() as conn:
                conn.execute("SELECT 1")
            components["sqlite"] = "ok"
        else:
            components["sqlite"] = "uninitialized"
            ready = False
    except Exception:
        components["sqlite"] = "error"
        ready = False
    try:
        if store is not None and store.ping():
            components["qdrant"] = "ok"
        else:
            components["qdrant"] = "error"
            ready = False
    except Exception:
        components["qdrant"] = "error"
        ready = False
    payload = HealthResponse(
        status="ok",
        version="1.0.0",
        ready=ready,
        components=components,
    )
    cfg: OwnerConfig | None = getattr(request.app.state, "cfg", None)
    production = cfg is not None and (cfg.app_env or "").lower() == "production"
    if not ready and production:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
        )
    return payload


@app.get("/metrics", tags=["system"])
async def metrics(request: Request) -> dict:
    """Privacy-safe counters: no questions, documents, or keys."""
    db: DatabaseManager | None = getattr(request.app.state, "db", None)
    return metrics_snapshot(db)


_TERMS_PATH = Path(__file__).resolve().parent.parent.parent / "TERMS.md"


@app.get("/terms", tags=["system"])
async def terms_text() -> FileResponse:
    """Public terms and privacy note shown before the first upload."""
    if not _TERMS_PATH.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms not found")
    return FileResponse(path=_TERMS_PATH, media_type="text/markdown", filename="TERMS.md")


# ---------------------------------------------------------------------------
# POST /session  (P5-T1: issue session token, server-derives scope)
# ---------------------------------------------------------------------------


def _set_session_cookie(response: Response, session_id: str, cfg: OwnerConfig) -> None:
    response.set_cookie(
        key="session_token",
        value=session_id,
        httponly=True,
        secure=(cfg.app_env or "").lower() == "production",
        samesite="lax",
        max_age=int(cfg.session_ttl_hours * 3600),
        path="/",
    )


@app.get(
    "/session",
    response_model=SessionCreateResponse,
    tags=["session"],
    summary="Resume the HttpOnly session cookie if it is still valid",
)
async def resume_session_endpoint(request: Request, response: Response) -> SessionCreateResponse:
    """Refresh does not mint a new quota. Private tabs still share the per-IP budget."""
    db: DatabaseManager = request.app.state.db
    cfg: OwnerConfig = getattr(request.app.state, "cfg", None) or OwnerConfig()
    token = request.cookies.get("session_token")
    authorization = request.headers.get("Authorization") or ""
    if not token and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session to resume. Call POST /session to begin.",
        )
    resumed = resume_session(db=db, token=token)
    _set_session_cookie(response, resumed.session_id, cfg)
    return resumed


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
    response: Response,
) -> SessionCreateResponse:
    """Create a new session and return a bearer token plus an HttpOnly cookie."""
    db: DatabaseManager = request.app.state.db
    created = create_session(db=db, visitor_keys=visitor_keys)
    cfg: OwnerConfig = getattr(request.app.state, "cfg", None) or OwnerConfig()
    _set_session_cookie(response, created.session_id, cfg)
    return created


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

# Demo PDFs for the Tier A preview iframe. Registered as a route (not a
# catch-all mount) so it stays ahead of the SPA StaticFiles mount at "/".
_DEMO_CORPUS_DIR = Path(__file__).resolve().parent.parent.parent / "demo_corpus"


@app.get("/demo_corpus/{filename}", include_in_schema=False)
async def serve_demo_pdf(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    pdf_path = _DEMO_CORPUS_DIR / safe_name
    if not pdf_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=safe_name,
        content_disposition_type="inline",
    )


# ---------------------------------------------------------------------------
# Mount React Single-Page Application (frontend-react/dist)
# ---------------------------------------------------------------------------
react_dist = Path(__file__).resolve().parent.parent.parent / "frontend-react" / "dist"
if react_dist.exists():
    app.mount("/", StaticFiles(directory=str(react_dist), html=True), name="frontend")




