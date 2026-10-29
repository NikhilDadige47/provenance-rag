"""Session lifecycle management with server-derived scope enforcement.

Implements roadmap P5-T1 & architecture §4.1, §6, §9:
- POST /session: issues a cryptographically random session token
- FastAPI dependency that maps token → scope (server always derives scope, clients never supply it)
- Session creation, expiry calculation, and retrieval from SQLite
- Server-enforced scope filter: [session_id, "demo"] injected by middleware, not the client

Security invariant: scope is ALWAYS derived server-side from the validated session token.
Clients cannot inject, override, or pass scope values directly.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.security.config import AccessTier, OwnerConfig, VisitorKeys, detect_access_tier
from src.security.secret import Secret
from src.storage.db import DatabaseManager

logger = logging.getLogger(__name__)

SESSION_TOKEN_BYTES = 32  # 256-bit entropy
SESSION_TOKEN_PREFIX = "prov_sess_"

_cfg = OwnerConfig.from_env()


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------


class SessionCreateResponse(BaseModel):
    """Response body for POST /session."""

    session_id: str = Field(description="Opaque session token (bearer or cookie value)")
    tier: str = Field(description="Access tier: tier_a_demo | tier_b_upload | tier_c_byok")
    expires_at: str = Field(description="ISO-8601 expiry timestamp (UTC)")
    message: str = Field(description="Human-readable summary of session capabilities")


class SessionState(BaseModel):
    """Server-side view of a session's current state (never sent to client verbatim)."""

    session_id: str
    scope: str  # same as session_id — the canonical Qdrant filter value
    tier: AccessTier
    expires_at: str
    chunks_embedded: int = 0
    rerank_calls: int = 0
    questions_owner_llm: int = 0
    questions_own_llm: int = 0
    request_count: int = 0
    is_expired: bool = False


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------


def _generate_token() -> str:
    """Generate a cryptographically secure, URL-safe session token."""
    return SESSION_TOKEN_PREFIX + secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def _compute_expiry() -> str:
    """Return an ISO-8601 expiry timestamp (UTC) based on configured session TTL."""
    cfg = OwnerConfig.from_env()
    expiry = datetime.now(UTC) + timedelta(hours=cfg.session_ttl_hours)
    return expiry.isoformat()


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------


def create_session(
    db: DatabaseManager,
    visitor_keys: VisitorKeys | None = None,
) -> SessionCreateResponse:
    """Create a new session record in SQLite and return a signed session token.

    The tier is determined server-side from visitor_keys (if provided during session creation).
    Visitors cannot supply their own session_id or tier.
    """
    session_id = _generate_token()
    expires_at = _compute_expiry()
    tier = detect_access_tier(visitor_keys or VisitorKeys())

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (session_id, created_at, expires_at, tier)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, datetime.now(UTC).isoformat(), expires_at, tier.value),
        )
        conn.commit()

    logger.info(f"Session created: id={session_id[:20]}... tier={tier.value} expires={expires_at}")

    tier_messages = {
        AccessTier.TIER_A_DEMO: (
            "Welcome! You can chat over the demo corpus with no setup required. "
            f"Owner-funded questions are limited to {_cfg.session_max_questions_owner_llm} per day "
            "on this connection."
        ),
        AccessTier.TIER_B_UPLOAD: (
            "Tier B active. You can upload PDFs with the free local parser or your own parser key. "
            "Answers use the owner's default LLM within session caps."
        ),
        AccessTier.TIER_C_BYOK: (
            "Tier C active. Your own LLM key is in use — "
            f"up to {_cfg.session_max_questions_own_llm} questions per session."
        ),
    }

    return SessionCreateResponse(
        session_id=session_id,
        tier=tier.value,
        expires_at=expires_at,
        message=tier_messages[tier],
    )


def resume_session(db: DatabaseManager, token: str) -> SessionCreateResponse:
    """Return the existing session if the token is still valid.

    Raises HTTP 401 when the token is missing, unknown, or expired.
    """
    state = _load_and_validate_session(token, db)
    return SessionCreateResponse(
        session_id=state.session_id,
        tier=state.tier.value,
        expires_at=state.expires_at,
        message="Session resumed. Owner-funded question budget is shared across tabs for today.",
    )


# ---------------------------------------------------------------------------
# Session validation helper
# ---------------------------------------------------------------------------


def _load_and_validate_session(token: str, db: DatabaseManager) -> SessionState:
    """Load session from DB, validate expiry, and return its state.

    Raises:
        HTTPException 401 if token is missing, unknown, or expired.
    """
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (token,),
        )
        row = cursor.fetchone()

    if row is None:
        logger.warning(f"Unknown session token: {token[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token. Call POST /session to begin a new session.",
        )

    row_dict = dict(row)

    # Check expiry
    expires_at_str: str | None = row_dict.get("expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(UTC) > expires_at:
            logger.info(f"Expired session token: {token[:20]}...")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has expired. Call POST /session to begin a new session.",
            )

    return SessionState(
        session_id=row_dict["session_id"],
        scope=row_dict["session_id"],  # scope == session_id by design
        tier=AccessTier(row_dict.get("tier", AccessTier.TIER_A_DEMO.value)),
        expires_at=row_dict.get("expires_at", ""),
        chunks_embedded=row_dict.get("chunks_embedded", 0),
        rerank_calls=row_dict.get("rerank_calls", 0),
        questions_owner_llm=row_dict.get("questions_owner_llm", 0),
        questions_own_llm=row_dict.get("questions_own_llm", 0),
        request_count=row_dict.get("request_count", 0),
    )


# ---------------------------------------------------------------------------
# FastAPI dependency: server-derived scope
# ---------------------------------------------------------------------------


def _extract_token_from_request(
    authorization: Annotated[str | None, Header()] = None,
    session_token: Annotated[str | None, Cookie()] = None,
) -> str | None:
    """Extract the session token from Authorization: Bearer header or HTTP-only cookie."""
    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    if session_token:
        return session_token.strip()
    return None


async def get_current_session(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    session_token: Annotated[str | None, Cookie()] = None,
) -> SessionState:
    """FastAPI dependency that enforces server-derived scope.

    Usage:
        @router.post("/chat")
        async def chat(session: SessionState = Depends(get_current_session)):
            scope = session.scope  # server-derived; never client-supplied

    Security: clients supply only the session token; the server looks up its
    corresponding scope. Client-supplied filter parameters are ignored.
    """
    token = _extract_token_from_request(authorization=authorization, session_token=session_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Include 'Authorization: Bearer <token>' or 'session_token' cookie.",
        )

    db: DatabaseManager = request.app.state.db
    return _load_and_validate_session(token, db)


# Convenience type alias for route signatures
CurrentSession = Annotated[SessionState, Depends(get_current_session)]


# ---------------------------------------------------------------------------
# LLM key extraction dependency
# ---------------------------------------------------------------------------


async def get_visitor_llm_key(
    x_llm_key: Annotated[str | None, Header(alias="X-LLM-Key")] = None,
    x_llm_provider: Annotated[str | None, Header(alias="X-LLM-Provider")] = None,
    x_llm_model: Annotated[str | None, Header(alias="X-LLM-Model")] = None,
) -> VisitorKeys:
    """Extract optional BYOK LLM credentials from request headers.

    The LLM key is request-scoped only: read from the header, used for this request,
    and never persisted to any storage medium.
    """
    llm_key: Secret | None = None
    if x_llm_key and x_llm_key.strip():
        llm_key = Secret(x_llm_key.strip())

    return VisitorKeys(
        llm_provider=x_llm_provider,
        llm_key=llm_key,
        llm_model=x_llm_model,
    )


VisitorLLMKeys = Annotated[VisitorKeys, Depends(get_visitor_llm_key)]
