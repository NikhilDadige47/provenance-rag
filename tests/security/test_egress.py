"""Tests for the egress allowlist and outbound network security."""

import pytest

from src.security.egress import (
    ALLOWED_EGRESS_HOSTS,
    create_secure_client,
    validate_egress_url,
)
from src.security.errors import EgressBlockedError


def test_allowed_hosts_pass_validation() -> None:
    for host in ALLOWED_EGRESS_HOSTS:
        url = f"https://{host}/v1/test"
        assert validate_egress_url(url) == url


def test_blocked_external_domain_raises_error() -> None:
    forbidden_urls = [
        "https://malicious-site.com/steal-data",
        "https://webhook.site/my-uuid",
        "https://google.com",
        "https://evil-parser.io/parse",
    ]
    for url in forbidden_urls:
        with pytest.raises(EgressBlockedError) as exc_info:
            validate_egress_url(url)
        assert "blocked" in str(exc_info.value).lower()


def test_blocked_private_and_loopback_ips() -> None:
    dangerous_ips = [
        "https://127.0.0.1:8000/internal",
        "https://10.0.0.1/admin",
        "https://192.168.1.1/secret",
        "https://172.16.0.5/conf",
        "https://169.254.169.254/latest/meta-data/",  # AWS metadata service
    ]
    for url in dangerous_ips:
        with pytest.raises(EgressBlockedError) as exc_info:
            validate_egress_url(url, allow_local_qdrant=False)
        assert (
            "blocked" in str(exc_info.value).lower() or "prohibited" in str(exc_info.value).lower()
        )


def test_insecure_http_scheme_rejected_for_cloud() -> None:
    with pytest.raises(EgressBlockedError) as exc_info:
        validate_egress_url("http://api.cohere.com/v1/embed")
    assert "insecure scheme" in str(exc_info.value).lower()


def test_local_qdrant_exception() -> None:
    # Local Qdrant allowed in dev mode
    assert validate_egress_url("http://localhost:6333/collections", allow_local_qdrant=True)
    assert validate_egress_url("http://127.0.0.1:6333/collections", allow_local_qdrant=True)

    # But blocked when allow_local_qdrant is False
    with pytest.raises(EgressBlockedError):
        validate_egress_url("http://localhost:6333/collections", allow_local_qdrant=False)


@pytest.mark.asyncio
async def test_secure_async_client_blocks_disallowed_host() -> None:
    client = create_secure_client(allow_local_qdrant=False)
    try:
        with pytest.raises(EgressBlockedError):
            await client.get("https://unauthorized-destination.com")
    finally:
        await client.aclose()
