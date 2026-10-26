"""Privacy-safe structured logging for API paths.

Implements roadmap P5-T6 & architecture §9.2 (tracing policy):
- Logs ONLY operational metadata: request_id, tier, timings, token counts, status.
- NEVER logs: question text, document text, API keys, or any visitor PII.
- Key-leak grep test is run via tests/api/test_privacy_logging.py.
- Provides structured log records as plain dicts for easy downstream processing.

Usage:
    from src.api.logging import log_chat_request, log_chat_response
"""

import logging
import re
import uuid

logger = logging.getLogger("provenance_rag.api")

# Patterns that must NEVER appear in log output
# These are tested by tests/api/test_privacy_logging.py
_KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9\-_]{10,}", re.IGNORECASE),  # OpenAI
    re.compile(r"gsk_[A-Za-z0-9\-_]{10,}", re.IGNORECASE),  # Groq
    re.compile(r"co-[A-Za-z0-9\-_]{10,}", re.IGNORECASE),  # Cohere
    re.compile(r"ant-[A-Za-z0-9\-_]{10,}", re.IGNORECASE),  # Anthropic (non-std)
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{10,}", re.IGNORECASE),  # Anthropic std
    re.compile(r"llx-[A-Za-z0-9\-_]{10,}", re.IGNORECASE),  # LlamaParse
    re.compile(r"prov_sess_[A-Za-z0-9\-_]{10,}", re.IGNORECASE),  # Session tokens
]


def generate_request_id() -> str:
    """Generate a short, collision-resistant request identifier."""
    return "req_" + uuid.uuid4().hex[:12]


def redact_keys(value: str) -> str:
    """Replace any detected API keys or session tokens in a string with '***'."""
    result = value
    for pattern in _KEY_PATTERNS:
        result = pattern.sub("***", result)
    return result


def contains_key(value: str) -> bool:
    """Return True if value contains any detectable API key pattern."""
    return any(p.search(value) for p in _KEY_PATTERNS)


def log_chat_request(
    *,
    request_id: str,
    tier: str,
    scope_prefix: str,  # Only first 8 chars of scope (not the full token)
    has_visitor_key: bool,
    question_length: int,  # Only length; never the question text itself
    history_turns: int,
) -> None:
    """Log an incoming /chat request with NO content data."""
    logger.info(
        "chat_request",
        extra={
            "event": "chat_request",
            "request_id": request_id,
            "tier": tier,
            "scope_prefix": scope_prefix,
            "has_visitor_key": has_visitor_key,
            "question_length_chars": question_length,
            "history_turns": history_turns,
        },
    )


def log_chat_response(
    *,
    request_id: str,
    tier: str,
    is_found: bool,
    is_grounded: bool,
    used_visitor_key: bool,
    answer_length: int,  # Only length; never the answer text itself
    source_count: int,
    timings: dict,
    tokens_used: int,
) -> None:
    """Log the outcome of a /chat request with NO content data."""
    logger.info(
        "chat_response",
        extra={
            "event": "chat_response",
            "request_id": request_id,
            "tier": tier,
            "is_found": is_found,
            "is_grounded": is_grounded,
            "used_visitor_key": used_visitor_key,
            "answer_length_chars": answer_length,
            "source_count": source_count,
            "timings_ms": timings,
            "tokens_used": tokens_used,
        },
    )


def log_cap_event(
    *,
    event: str,  # "session_owner_llm_cap", "daily_cap", "rate_limit", etc.
    request_id: str,
    tier: str,
    scope_prefix: str,
    detail: str,
) -> None:
    """Log a rate-limit or cap trigger event."""
    logger.warning(
        event,
        extra={
            "event": event,
            "request_id": request_id,
            "tier": tier,
            "scope_prefix": scope_prefix,
            "detail": detail,
        },
    )


def log_session_created(*, session_id_prefix: str, tier: str) -> None:
    """Log session creation (prefix only — not the full session token)."""
    logger.info(
        "session_created",
        extra={
            "event": "session_created",
            "session_id_prefix": session_id_prefix,
            "tier": tier,
        },
    )
