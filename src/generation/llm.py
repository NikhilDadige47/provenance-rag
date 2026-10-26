"""LLM generation adapters with streaming and egress security.

Implements roadmap P4-T5 & architecture §5, §7:
- Owner default LLM adapter (Groq with capped output tokens)
- BYOK LLM adapter #1 (OpenAI via visitor key)
- BYOK LLM adapter #2 (Anthropic via visitor key)
- Factory resolving owner default vs visitor key
- Stream token generator supporting real-time terminal & browser updates
- Fail-fast error taxonomy for visitor key authentication errors
"""

import json
import logging
from collections.abc import AsyncIterator

from src.interfaces import ILLM
from src.security.config import OwnerConfig
from src.security.egress import SecureHttpClient
from src.security.errors import (
    InvalidKeyError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.security.secret import Secret

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.1


class GroqLLM(ILLM):
    """Groq API adapter (Default Owner LLM or Visitor BYOK)."""

    def __init__(
        self,
        api_key: Secret | None = None,
        model: str | None = None,
        is_visitor_key: bool = False,
    ) -> None:
        cfg = OwnerConfig.from_env()
        self._api_key = api_key if api_key is not None else cfg.default_llm_api_key
        self._model = model or cfg.default_llm_model or "llama-3.3-70b-versatile"
        self._is_visitor_key = is_visitor_key
        self._http_client = SecureHttpClient.create_async_client()

    @property
    def provider_name(self) -> str:
        return "groq"

    async def generate_stream(
        self, prompt: str, api_key: Secret | None = None, model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream generated response tokens from Groq."""
        active_key = api_key or self._api_key
        active_model = model or self._model

        if not active_key or not active_key.reveal():
            raise InvalidKeyError(provider="groq", is_visitor_key=self._is_visitor_key)

        headers = {
            "Authorization": f"Bearer {active_key.reveal()}",
            "Content-Type": "application/json",
            "User-Agent": "ProvenanceRAG/1.0",
        }

        payload = {
            "model": active_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": DEFAULT_OUTPUT_TOKENS,
            "temperature": DEFAULT_TEMPERATURE,
            "stream": True,
        }

        async with self._http_client.stream(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30.0,
        ) as response:
            if response.status_code == 401 or response.status_code == 403:
                raise InvalidKeyError(provider="groq", is_visitor_key=self._is_visitor_key)
            if response.status_code == 429:
                raise RateLimitedError(provider="groq", is_visitor_key=self._is_visitor_key)
            if response.status_code != 200:
                raise ProviderUnavailableError(provider="groq", status_code=response.status_code)

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[len("data: ") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except json.JSONDecodeError:
                    continue


class OpenAILLM(ILLM):
    """OpenAI API adapter for visitor BYOK keys."""

    def __init__(
        self,
        api_key: Secret | None = None,
        model: str = "gpt-4o-mini",
        is_visitor_key: bool = True,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._is_visitor_key = is_visitor_key
        self._http_client = SecureHttpClient.create_async_client()

    @property
    def provider_name(self) -> str:
        return "openai"

    async def generate_stream(
        self, prompt: str, api_key: Secret | None = None, model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream generated response tokens from OpenAI."""
        active_key = api_key or self._api_key
        active_model = model or self._model

        if not active_key or not active_key.reveal():
            raise InvalidKeyError(provider="openai", is_visitor_key=self._is_visitor_key)

        headers = {
            "Authorization": f"Bearer {active_key.reveal()}",
            "Content-Type": "application/json",
            "User-Agent": "ProvenanceRAG/1.0",
        }

        payload = {
            "model": active_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": DEFAULT_OUTPUT_TOKENS,
            "temperature": DEFAULT_TEMPERATURE,
            "stream": True,
        }

        async with self._http_client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30.0,
        ) as response:
            if response.status_code in (401, 403):
                raise InvalidKeyError(provider="openai", is_visitor_key=self._is_visitor_key)
            if response.status_code == 429:
                raise QuotaExhaustedError(provider="openai", is_visitor_key=self._is_visitor_key)
            if response.status_code != 200:
                raise ProviderUnavailableError(provider="openai", status_code=response.status_code)

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[len("data: ") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except json.JSONDecodeError:
                    continue


class AnthropicLLM(ILLM):
    """Anthropic API adapter for visitor BYOK keys."""

    def __init__(
        self,
        api_key: Secret | None = None,
        model: str = "claude-3-5-haiku-20241022",
        is_visitor_key: bool = True,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._is_visitor_key = is_visitor_key
        self._http_client = SecureHttpClient.create_async_client()

    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def generate_stream(
        self, prompt: str, api_key: Secret | None = None, model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream generated response tokens from Anthropic Messages API."""
        active_key = api_key or self._api_key
        active_model = model or self._model

        if not active_key or not active_key.reveal():
            raise InvalidKeyError(provider="anthropic", is_visitor_key=self._is_visitor_key)

        headers = {
            "x-api-key": active_key.reveal(),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "ProvenanceRAG/1.0",
        }

        payload = {
            "model": active_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": DEFAULT_OUTPUT_TOKENS,
            "temperature": DEFAULT_TEMPERATURE,
            "stream": True,
        }

        async with self._http_client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers,
            timeout=30.0,
        ) as response:
            if response.status_code in (401, 403):
                raise InvalidKeyError(provider="anthropic", is_visitor_key=self._is_visitor_key)
            if response.status_code == 429:
                raise QuotaExhaustedError(provider="anthropic", is_visitor_key=self._is_visitor_key)
            if response.status_code != 200:
                raise ProviderUnavailableError(
                    provider="anthropic", status_code=response.status_code
                )

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[len("data: ") :].strip()
                try:
                    chunk = json.loads(data_str)
                    event_type = chunk.get("type")
                    if event_type == "content_block_delta":
                        delta = chunk.get("delta", {})
                        text = delta.get("text", "")
                        if text:
                            yield text
                except json.JSONDecodeError:
                    continue


def get_llm_adapter(
    provider: str | None = None,
    api_key: Secret | None = None,
    model: str | None = None,
) -> ILLM:
    """Factory creating the appropriate ILLM instance based on visitor vs owner credentials."""
    # If visitor provides a valid key, instantiate the corresponding BYOK adapter
    if api_key and bool(api_key.reveal()):
        provider_norm = (provider or "openai").lower()
        if provider_norm == "openai":
            return OpenAILLM(api_key=api_key, model=model or "gpt-4o-mini", is_visitor_key=True)
        elif provider_norm == "anthropic":
            return AnthropicLLM(
                api_key=api_key, model=model or "claude-3-5-haiku-20241022", is_visitor_key=True
            )
        elif provider_norm == "groq":
            return GroqLLM(
                api_key=api_key, model=model or "llama-3.3-70b-versatile", is_visitor_key=True
            )
        else:
            raise ValueError(f"Unsupported BYOK LLM provider '{provider_norm}'.")

    # Fallback to Owner Default LLM (Groq)
    return GroqLLM(is_visitor_key=False)
