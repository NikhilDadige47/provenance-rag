"""Security package for Provenance RAG.

Handles Secret wrapper, key redaction, egress domain allowlisting, and owner spend protection.
"""

from src.security.config import AccessTier, OwnerConfig, VisitorKeys, detect_access_tier
from src.security.egress import SecureHttpClient, create_secure_client
from src.security.errors import (
    EgressBlockedError,
    InvalidKeyError,
    KeySecurityError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.security.redaction import RedactionFilter, redact_dict, redact_text
from src.security.secret import Secret

__all__ = [
    "AccessTier",
    "EgressBlockedError",
    "InvalidKeyError",
    "KeySecurityError",
    "OwnerConfig",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "QuotaExhaustedError",
    "RateLimitedError",
    "RedactionFilter",
    "Secret",
    "SecureHttpClient",
    "VisitorKeys",
    "create_secure_client",
    "detect_access_tier",
    "redact_dict",
    "redact_text",
]
