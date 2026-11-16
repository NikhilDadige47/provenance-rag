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
        description="Name of the provider (e.g., llamaparse, groq, openai, cohere, ollama)"
    )
    key: Secret | None = Field(default=None, description="API key to validate")
    base_url: str | None = Field(
        default=None, description="Custom base URL for local/OpenAI-compatible endpoints"
    )


class ConnectionTestResponse(BaseModel):
    ok: bool
    provider: str
    error: str | None = None
    hint: str | None = None
    models: list[str] | None = None


async def verify_provider_connection(
    provider: str,
    key: Secret | None = None,
    client: httpx.AsyncClient | None = None,
    base_url: str | None = None,
) -> ConnectionTestResponse:
    """Validate a provider key or local endpoint with the cheapest non-credit-consuming call."""
    provider_clean = provider.strip().lower()

    # Free local parsers and owner-paid auto waterfall don't need a visitor key
    if provider_clean in {"local_pymupdf", "auto"}:
        return ConnectionTestResponse(ok=True, provider=provider_clean)

    # Local LLMs (Ollama, LM Studio, LocalAI)
    if provider_clean in {"ollama", "local", "lmstudio"}:
        base = (base_url or "http://127.0.0.1:11434/v1").strip().rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"

        candidate_bases = [base]
        if "localhost" in base:
            candidate_bases.append(base.replace("localhost", "127.0.0.1"))
        elif "127.0.0.1" in base:
            candidate_bases.append(base.replace("127.0.0.1", "localhost"))

        headers: dict[str, str] = {}
        if key and key.reveal():
            headers["Authorization"] = f"Bearer {key.reveal()}"

        local_client = create_secure_client(allow_local_llm=True)
        try:
            for probe_base in candidate_bases:
                probe_url = f"{probe_base}/models"
                try:
                    response = await local_client.get(probe_url, headers=headers, timeout=4.0)
                    if response.status_code == 200:
                        data = response.json()
                        models: list[str] = []
                        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                            models = [m["id"] for m in data["data"] if isinstance(m, dict) and "id" in m]
                        return ConnectionTestResponse(
                            ok=True,
                            provider=provider_clean,
                            models=models if models else ["llama3.2:3b", "llama3.1:8b"],
                        )
                except Exception:
                    continue

            return ConnectionTestResponse(
                ok=False,
                provider=provider_clean,
                error=f"Unable to connect to local model server at {base}.",
                hint="Ensure your local model runner is running (e.g. 'OLLAMA_ORIGINS=\"*\" ollama serve' or LM Studio).",
            )
        finally:
            await local_client.aclose()

    if provider_clean not in PROVIDER_PROBE_URLS:
        return ConnectionTestResponse(
            ok=False,
            provider=provider_clean,
            error=f"Unsupported provider '{provider}'.",
            hint="Supported providers: " + ", ".join(PROVIDER_PROBE_URLS.keys()),
        )

    # Cloud providers require an API key
    if not key or not key.reveal() or not key.reveal().strip():
        return ConnectionTestResponse(
            ok=False,
            provider=provider_clean,
            error="No API key provided.",
            hint=f"Please enter a valid {provider_clean.upper()} API key.",
        )

    clean_key = key.reveal().strip()
    probe_url = PROVIDER_PROBE_URLS[provider_clean]
    headers: dict[str, str] = {}

    if provider_clean == "gemini":
        probe_url = f"{probe_url}?key={clean_key}"
    elif provider_clean in {"cohere", "openai", "groq", "mistral", "llamaparse", "landingai", "unstructured"}:
        headers["Authorization"] = f"Bearer {clean_key}"
    elif provider_clean == "anthropic":
        headers["x-api-key"] = clean_key
        headers["anthropic-version"] = "2023-06-01"

    close_client = False
    if client is None:
        client = create_secure_client()
        close_client = True

    try:
        response = await client.get(probe_url, headers=headers, timeout=10.0)

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

        # Gemini returns 400 for invalid API keys (not 401/403)
        if provider_clean == "gemini" and response.status_code == 400:
            raise InvalidKeyError(provider=provider_clean, is_visitor_key=True)

        if response.status_code == 429:
            raise RateLimitedError(provider=provider_clean, is_visitor_key=True)

        # Anthropic may return 404 if the models endpoint is not available for the
        # API version used — treat any non-auth-failure as "key accepted" for providers
        # whose auth check occurs before routing and would have returned 401/403 if the
        # key were bad.
        if provider_clean == "anthropic" and response.status_code in {404, 405}:
            return ConnectionTestResponse(ok=True, provider=provider_clean)

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
        return ConnectionTestResponse(
            ok=False,
            provider=provider_clean,
            error=f"Request to {provider_clean} timed out.",
            hint="The provider service did not respond in time or may be experiencing degradation.",
        )
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
