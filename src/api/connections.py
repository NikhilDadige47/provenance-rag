"""Connection testing service for visitor and owner credentials.

Provides fast, cheap validation endpoints that verify API keys before
documents are uploaded or chat queries are run, without burning credits or leaking keys.
"""

import httpx
from pydantic import BaseModel, Field

from src.security.egress import create_secure_client
from src.security.errors import (
    EgressBlockedError,
    InvalidKeyError,
    ProviderTimeoutError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.security.secret import Secret

PROVIDER_PROBE_URLS = {
    "cohere": "https://api.cohere.com/v1/check-api-key",
    "openai": "https://api.openai.com/v1/models",
    "groq": "https://api.groq.com/openai/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
    "mistral": "https://api.mistral.ai/v1/models",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "llamaparse": "https://api.cloud.llamaindex.ai/api/v1/parsing/supported-file-extensions",
    "landingai": "https://api.va.landing.ai/v1/tools/agentic-document-analysis",
    "unstructured": "https://api.unstructured.io",
}


class ConnectionTestRequest(BaseModel):
    provider: str = Field(
        description="Name of the provider (e.g., llamaparse, groq, openai, cohere)"
    )
    key: Secret = Field(description="API key to validate")


class ConnectionTestResponse(BaseModel):
    ok: bool
    provider: str
    error: str | None = None
    hint: str | None = None
    models: list[str] | None = None


async def verify_provider_connection(
    provider: str,
    key: Secret,
    client: httpx.AsyncClient | None = None,
) -> ConnectionTestResponse:
    """Validate a provider key with the cheapest non-credit-consuming call."""
    provider_clean = provider.strip().lower()

    # Free local parsers don't need a key
    if provider_clean in {"local_pymupdf", "local"}:
        return ConnectionTestResponse(ok=True, provider=provider_clean)

    if provider_clean not in PROVIDER_PROBE_URLS:
        return ConnectionTestResponse(
            ok=False,
            provider=provider_clean,
            error=f"Unsupported provider '{provider}'.",
            hint="Supported providers: " + ", ".join(PROVIDER_PROBE_URLS.keys()),
        )

    probe_url = PROVIDER_PROBE_URLS[provider_clean]
    headers: dict[str, str] = {}

    if provider_clean == "gemini":
        probe_url = f"{probe_url}?key={key.reveal()}"
    elif provider_clean in {"cohere", "openai", "groq", "mistral", "llamaparse", "landingai", "unstructured"}:
        headers["Authorization"] = f"Bearer {key.reveal()}"
    elif provider_clean == "anthropic":
        headers["x-api-key"] = key.reveal()
        headers["anthropic-version"] = "2023-06-01"

    close_client = False
    if client is None:
        client = create_secure_client()
        close_client = True

    try:
        response = await client.get(probe_url, headers=headers)

        if response.status_code in {200, 201}:
            models: list[str] | None = None
            try:
                data = response.json()
                if isinstance(data, dict):
                    if "data" in data and isinstance(data["data"], list):
                        models = [m["id"] for m in data["data"] if isinstance(m, dict) and "id" in m]
                    elif "models" in data and isinstance(data["models"], list):
                        models = [
                            m.get("id") or m.get("name", "").replace("models/", "")
                            for m in data["models"]
                            if isinstance(m, dict)
                        ]
            except Exception:
                pass
            return ConnectionTestResponse(ok=True, provider=provider_clean, models=models)

        # For certain APIs that require POST or specific endpoints, 404/405 without 401/403 can still verify auth
        if provider_clean in {"landingai", "unstructured"} and response.status_code not in {401, 403}:
            return ConnectionTestResponse(ok=True, provider=provider_clean)

        if response.status_code in {401, 403}:
            raise InvalidKeyError(provider=provider_clean, is_visitor_key=True)

        if response.status_code == 429:
            raise RateLimitedError(provider=provider_clean, is_visitor_key=True)

        return ConnectionTestResponse(
            ok=False,
            provider=provider_clean,
            error=f"Provider returned status {response.status_code}.",
            hint="Check provider service status and API permissions.",
        )

    except InvalidKeyError as e:
        return ConnectionTestResponse(
            ok=False,
            provider=provider_clean,
            error=e.message,
            hint="Please check the provider console to make sure the key is valid and not expired.",
        )
    except (RateLimitedError, QuotaExhaustedError) as e:
        return ConnectionTestResponse(
            ok=False,
            provider=provider_clean,
            error=e.message,
            hint="Account rate limit or credit quota was exceeded.",
        )
    except httpx.TimeoutException:
        raise ProviderTimeoutError(provider=provider_clean) from None
    except EgressBlockedError as e:
        return ConnectionTestResponse(
            ok=False,
            provider=provider_clean,
            error="Egress blocked by security policy.",
            hint=str(e),
        )
    except Exception as e:
        return ConnectionTestResponse(
            ok=False,
            provider=provider_clean,
            error="Unable to connect to provider.",
            hint=str(e),
        )
    finally:
        if close_client and client is not None:
            await client.aclose()
