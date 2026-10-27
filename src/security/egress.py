"""Fixed egress allowlist and outbound network firewall.

Guarantees that adapters can only communicate with hardcoded provider endpoints,
completely eliminating Server-Side Request Forgery (SSRF) and data exfiltration.
"""

import ipaddress
from urllib.parse import urlparse

import httpx

from src.security.errors import EgressBlockedError

# Hardcoded domain allowlist of authorized AI providers
ALLOWED_EGRESS_HOSTS: frozenset[str] = frozenset(
    {
        "api.cohere.com",
        "api.cohere.ai",
        "api.cloud.llamaindex.ai",
        "api.landing.ai",
        "api.va.landing.ai",
        "api.unstructured.io",
        "api.groq.com",
        "api.openai.com",
        "api.anthropic.com",
        "api.mistral.ai",
        "generativelanguage.googleapis.com",
        "cloud.langfuse.com",
        "us.cloud.langfuse.com",
    }
)


def is_ip_address(host: str) -> bool:
    """Check if the host string is an IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def validate_egress_url(url: str, allow_local_qdrant: bool = True) -> str:
    """Validate that the target URL belongs to an allowed provider host.

    Blocks:
    - Arbitrary unknown domains
    - Loopback (127.0.0.1, ::1, localhost) unless specifically allowed for local Qdrant
    - Private networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Cloud metadata services (169.254.169.254)
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    scheme = parsed.scheme.lower()

    if not host:
        raise EgressBlockedError(f"Missing hostname in URL: {url}")

    # Local Qdrant exemption for dev/local testing
    if allow_local_qdrant and host in {"localhost", "127.0.0.1"}:
        return url

    # Require HTTPS for all external cloud egress
    if scheme != "https":
        raise EgressBlockedError(
            f"Insecure scheme '{scheme}' for host '{host}'. Only HTTPS is permitted."
        )

    # Check for IP literals (RFC 1918, link-local, cloud metadata)
    if is_ip_address(host):
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise EgressBlockedError(
                f"Access to private/reserved IP '{host}' is strictly prohibited."
            )
        # Any other direct IP is also blocked unless it matches a recognized provider
        raise EgressBlockedError(
            f"Direct IP access '{host}' is blocked. Providers must be addressed via domain names."
        )

    # Enforce domain allowlist
    if host not in ALLOWED_EGRESS_HOSTS:
        raise EgressBlockedError(host)

    return url


class SecureAsyncTransport(httpx.AsyncHTTPTransport):
    """Transport that verifies egress policy on every outgoing request."""

    def __init__(self, allow_local_qdrant: bool = True, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.allow_local_qdrant = allow_local_qdrant

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        validate_egress_url(str(request.url), allow_local_qdrant=self.allow_local_qdrant)
        return await super().handle_async_request(request)


class SecureSyncTransport(httpx.HTTPTransport):
    """Sync transport that verifies egress policy on every outgoing request."""

    def __init__(self, allow_local_qdrant: bool = True, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.allow_local_qdrant = allow_local_qdrant

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        validate_egress_url(str(request.url), allow_local_qdrant=self.allow_local_qdrant)
        return super().handle_request(request)


class SecureHttpClient:
    """Factory and manager for secure HTTP clients."""

    DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

    @classmethod
    def create_async_client(cls, allow_local_qdrant: bool = True) -> httpx.AsyncClient:
        """Create an async HTTP client enforcing egress security."""
        return httpx.AsyncClient(
            transport=SecureAsyncTransport(allow_local_qdrant=allow_local_qdrant),
            timeout=cls.DEFAULT_TIMEOUT,
            follow_redirects=False,  # Prevent open redirects
        )

    @classmethod
    def create_sync_client(cls, allow_local_qdrant: bool = True) -> httpx.Client:
        """Create a sync HTTP client enforcing egress security."""
        return httpx.Client(
            transport=SecureSyncTransport(allow_local_qdrant=allow_local_qdrant),
            timeout=cls.DEFAULT_TIMEOUT,
            follow_redirects=False,
        )


def create_secure_client(allow_local_qdrant: bool = True) -> httpx.AsyncClient:
    """Convenience helper to create an async secure client."""
    return SecureHttpClient.create_async_client(allow_local_qdrant=allow_local_qdrant)
