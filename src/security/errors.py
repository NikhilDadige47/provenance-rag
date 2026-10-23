"""Standard error taxonomy for Provenance RAG security and provider operations.

Enforces clear separation between visitor-key errors (never retry)
and owner-key infrastructure errors (bounded retry).
"""

from typing import Any


class KeySecurityError(Exception):
    """Base exception for all security, key handling, and egress violations."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EgressBlockedError(KeySecurityError):
    """Raised when an outbound HTTP request targets a host outside the egress allowlist."""

    def __init__(self, target_host: str) -> None:
        super().__init__(
            f"Outbound request to host '{target_host}' was blocked by the security egress policy."
        )
        self.target_host = target_host


class InvalidKeyError(KeySecurityError):
    """Raised when an API key is rejected by the upstream provider.

    Visitor key: NEVER retry. Fail fast.
    """

    def __init__(self, provider: str, is_visitor_key: bool = True) -> None:
        entity = "Your" if is_visitor_key else "Owner"
        super().__init__(
            f"{entity} {provider} API key was rejected as invalid or unauthorized. Please verify the key."
        )
        self.provider = provider
        self.is_visitor_key = is_visitor_key
        self.retryable = False


class QuotaExhaustedError(KeySecurityError):
    """Raised when the API key has reached its provider spend or rate quota."""

    def __init__(self, provider: str, is_visitor_key: bool = True) -> None:
        entity = "Your" if is_visitor_key else "Owner"
        super().__init__(
            f"{entity} {provider} quota has been exhausted. Please check your provider account limits."
        )
        self.provider = provider
        self.is_visitor_key = is_visitor_key
        self.retryable = False


class RateLimitedError(KeySecurityError):
    """Raised when an upstream provider throttles requests."""

    def __init__(
        self,
        provider: str,
        is_visitor_key: bool = True,
        retry_after_seconds: float | None = None,
    ) -> None:
        entity = "Your" if is_visitor_key else "Owner"
        super().__init__(
            f"{entity} {provider} request rate limit exceeded."
            + (f" Retry after {retry_after_seconds}s." if retry_after_seconds else "")
        )
        self.provider = provider
        self.is_visitor_key = is_visitor_key
        # Visitor key errors should not be retried automatically by the server
        self.retryable = not is_visitor_key
        self.retry_after_seconds = retry_after_seconds


class ProviderTimeoutError(KeySecurityError):
    """Raised when an upstream provider fails to respond within the timeout window."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"Request to {provider} timed out. The provider service may be degraded.")
        self.provider = provider
        self.retryable = True


class ProviderUnavailableError(KeySecurityError):
    """Raised when an upstream provider returns 5xx or connection error."""

    def __init__(self, provider: str, status_code: int | None = None) -> None:
        super().__init__(
            f"Upstream provider {provider} is currently unavailable"
            + (f" (status {status_code})" if status_code else "")
        )
        self.provider = provider
        self.status_code = status_code
        self.retryable = True
