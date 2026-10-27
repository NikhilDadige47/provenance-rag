"""Logging filters, text sanitizers, and middleware to prevent secret leakage.

Ensures that API keys, bearer tokens, and sensitive headers are scrubbed before
reaching log streams, stack traces, or external clients.
"""

import logging
import re
from typing import Any

# Regex patterns matching key formats and credential headers
_PATTERNS = [
    # Bearer tokens
    # Common provider key prefixes
    (re.compile(r"\b(sk-[a-zA-Z0-9_\-]{16,})\b"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"\b(co-[a-zA-Z0-9_\-]{16,})\b"), "[REDACTED_COHERE_KEY]"),
    (re.compile(r"\b(gsk_[a-zA-Z0-9_\-]{16,})\b"), "[REDACTED_GROQ_KEY]"),
    (re.compile(r"\b(anthropic-[a-zA-Z0-9_\-]{16,})\b"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"\b(llx-[a-zA-Z0-9_\-]{16,})\b"), "[REDACTED_LLAMAPARSE_KEY]"),
    # Headers in raw text/logs: "authorization: Bearer ...", "x-api-key: ...", etc.
    (
        re.compile(
            r"((?:x-api-key|x-parser-key|x-llm-key|authorization):\s*(?:bearer\s+)?)[^\r\n,]+",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
    # Bearer tokens anywhere in text
    (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE), r"\1[REDACTED]"),
    # URL parameters like ?api_key=... or ?token=...
    (
        re.compile(r"((?:api[_-]?key|token|secret|password)=)[^&\s]+", re.IGNORECASE),
        r"\1[REDACTED]",
    ),
]

_SENSITIVE_KEY_NAMES = {
    "key",
    "apikey",
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
    "auth",
    "parser_key",
    "llm_key",
    "cohere_api_key",
    "qdrant_api_key",
}


def redact_text(text: str) -> str:
    """Scrub all known key formats and authorization patterns from arbitrary text."""
    if not text:
        return ""
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


redact_sensitive_str = redact_text


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively scrub sensitive keys from dictionaries (e.g., config dumps, request bodies)."""
    clean: dict[str, Any] = {}
    for k, v in data.items():
        k_normalized = k.lower().replace("-", "_")
        if any(s in k_normalized for s in _SENSITIVE_KEY_NAMES):
            clean[k] = "***"
        elif isinstance(v, dict):
            clean[k] = redact_dict(v)
        elif isinstance(v, list):
            clean[k] = [
                redact_dict(item)
                if isinstance(item, dict)
                else redact_text(str(item))
                if isinstance(item, str)
                else item
                for item in v
            ]
        elif isinstance(v, str):
            clean[k] = redact_text(v)
        else:
            clean[k] = v
    return clean


class RedactionFilter(logging.Filter):
    """Logging filter that scrubs sensitive strings and keys from all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_dict(record.args)
            elif isinstance(record.args, (tuple, list)):
                record.args = tuple(
                    redact_text(str(arg))
                    if isinstance(arg, str)
                    else redact_dict(arg)
                    if isinstance(arg, dict)
                    else arg
                    for arg in record.args
                )
        return True
