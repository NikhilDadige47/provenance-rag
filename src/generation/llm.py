"""LLM generation adapters with streaming and egress security.

Implements roadmap P4-T5 & architecture §5, §7:
- Owner default LLM adapter (Groq with capped output tokens)
- BYOK LLM adapter #1 (OpenAI via visitor key)
- BYOK LLM adapter #2 (Anthropic via visitor key)
- Factory resolving owner default vs visitor key
- Stream token generator supporting real-time terminal & browser updates
- Fail-fast error taxonomy for visitor key authentication errors
- Prompt + completion usage captured from provider stream metadata
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

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


@dataclass
class TokenUsage:
    """Prompt + completion tokens reported by a provider (or estimated as fallback)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return int(self.prompt_tokens or 0) + int(self.completion_tokens or 0)


def consume_usage(llm: ILLM, prompt: str = "", completion: str = "") -> TokenUsage:
    """Return usage from the last stream, falling back to a local estimate."""
    usage = getattr(llm, "_last_usage", None)
    llm._last_usage = TokenUsage()
    if isinstance(usage, TokenUsage) and usage.total_tokens > 0:
        return usage
    from src.ingest.chunking.tokenizer import estimate_tokens

    return TokenUsage(
        prompt_tokens=estimate_tokens(prompt) if prompt else 0,
        completion_tokens=estimate_tokens(completion) if completion else 0,
    )


def _usage_from_openai_dict(raw: dict | None) -> TokenUsage | None:
    if not isinstance(raw, dict):
        return None
    prompt = int(raw.get("prompt_tokens") or raw.get("input_tokens") or 0)
    completion = int(raw.get("completion_tokens") or raw.get("output_tokens") or 0)
    if prompt <= 0 and completion <= 0:
        total = int(raw.get("total_tokens") or 0)
        if total <= 0:
            return None
        return TokenUsage(prompt_tokens=total, completion_tokens=0)
    return TokenUsage(prompt_tokens=prompt, completion_tokens=completion)


async def _iter_openai_sse(
    response: object, usage_sink: list[TokenUsage] | None = None
) -> AsyncIterator[str]:
    """Yield text deltas from an OpenAI-compatible SSE chat stream."""
    async for line in response.aiter_lines():  # type: ignore[attr-defined]
        line = line.strip()
        if not line or not line.startswith("data: "):
            continue
        data_str = line[len("data: ") :].strip()
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        parsed = _usage_from_openai_dict(chunk.get("usage"))
        if parsed is not None and usage_sink is not None:
            usage_sink.append(parsed)
        choices = chunk.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta", {})
        content = delta.get("content", "")
        if content:
            yield content


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
        self,
        prompt: str,
        api_key: Secret | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
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

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": active_model,
            "messages": messages,
            "max_tokens": DEFAULT_OUTPUT_TOKENS,
            "temperature": temperature if temperature is not None else DEFAULT_TEMPERATURE,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        usage_sink: list[TokenUsage] = []
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

            async for content in _iter_openai_sse(response, usage_sink):
                yield content
        if usage_sink:
            self._last_usage = usage_sink[-1]


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
        self,
        prompt: str,
        api_key: Secret | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
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

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": active_model,
            "messages": messages,
            "max_tokens": DEFAULT_OUTPUT_TOKENS,
            "temperature": temperature if temperature is not None else DEFAULT_TEMPERATURE,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        usage_sink: list[TokenUsage] = []
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

            async for content in _iter_openai_sse(response, usage_sink):
                yield content
        if usage_sink:
            self._last_usage = usage_sink[-1]


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

            prompt_tokens = 0
            completion_tokens = 0
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[len("data: ") :].strip()
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                event_type = chunk.get("type")
                if event_type == "message_start":
                    msg_usage = (chunk.get("message") or {}).get("usage") or {}
                    prompt_tokens = int(msg_usage.get("input_tokens") or 0)
                    completion_tokens = int(msg_usage.get("output_tokens") or 0)
                elif event_type == "message_delta":
                    delta_usage = chunk.get("usage") or {}
                    if "output_tokens" in delta_usage:
                        completion_tokens = int(delta_usage.get("output_tokens") or completion_tokens)
                elif event_type == "content_block_delta":
                    delta = chunk.get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        yield text
            if prompt_tokens or completion_tokens:
                self._last_usage = TokenUsage(
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
                )


class MistralLLM(ILLM):
    """Mistral API adapter for visitor BYOK keys (OpenAI-compatible chat completions)."""

    def __init__(
        self,
        api_key: Secret | None = None,
        model: str = "mistral-small-latest",
        is_visitor_key: bool = True,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._is_visitor_key = is_visitor_key
        self._http_client = SecureHttpClient.create_async_client()

    @property
    def provider_name(self) -> str:
        return "mistral"

    async def generate_stream(
        self, prompt: str, api_key: Secret | None = None, model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream generated response tokens from Mistral."""
        active_key = api_key or self._api_key
        active_model = model or self._model

        if not active_key or not active_key.reveal():
            raise InvalidKeyError(provider="mistral", is_visitor_key=self._is_visitor_key)

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
            "stream_options": {"include_usage": True},
        }

        usage_sink: list[TokenUsage] = []
        async with self._http_client.stream(
            "POST",
            "https://api.mistral.ai/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30.0,
        ) as response:
            if response.status_code in (401, 403):
                raise InvalidKeyError(provider="mistral", is_visitor_key=self._is_visitor_key)
            if response.status_code == 429:
                raise QuotaExhaustedError(provider="mistral", is_visitor_key=self._is_visitor_key)
            if response.status_code != 200:
                raise ProviderUnavailableError(provider="mistral", status_code=response.status_code)
            async for content in _iter_openai_sse(response, usage_sink):
                yield content
        if usage_sink:
            self._last_usage = usage_sink[-1]


class GeminiLLM(ILLM):
    """Google Gemini adapter for visitor BYOK keys."""

    def __init__(
        self,
        api_key: Secret | None = None,
        model: str = "gemini-1.5-flash-latest",
        is_visitor_key: bool = True,
    ) -> None:
        self._api_key = api_key
        self._model = (model or "gemini-1.5-flash-latest").removeprefix("models/")
        self._is_visitor_key = is_visitor_key
        self._http_client = SecureHttpClient.create_async_client()

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def generate_stream(
        self, prompt: str, api_key: Secret | None = None, model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream generated response tokens from Gemini generateContent SSE."""
        active_key = api_key or self._api_key
        active_model = (model or self._model).removeprefix("models/")

        if not active_key or not active_key.reveal():
            raise InvalidKeyError(provider="gemini", is_visitor_key=self._is_visitor_key)

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{active_model}:streamGenerateContent?alt=sse&key={active_key.reveal()}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": DEFAULT_OUTPUT_TOKENS,
                "temperature": DEFAULT_TEMPERATURE,
            },
        }

        async with self._http_client.stream(
            "POST",
            url,
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ProvenanceRAG/1.0"},
            timeout=30.0,
        ) as response:
            if response.status_code in (400, 401, 403):
                raise InvalidKeyError(provider="gemini", is_visitor_key=self._is_visitor_key)
            if response.status_code == 429:
                raise QuotaExhaustedError(provider="gemini", is_visitor_key=self._is_visitor_key)
            if response.status_code != 200:
                raise ProviderUnavailableError(provider="gemini", status_code=response.status_code)

            prompt_tokens = 0
            completion_tokens = 0
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[len("data: ") :].strip()
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                meta = chunk.get("usageMetadata") or {}
                if meta:
                    prompt_tokens = int(meta.get("promptTokenCount") or prompt_tokens)
                    completion_tokens = int(
                        meta.get("candidatesTokenCount") or meta.get("totalTokenCount") or completion_tokens
                    )
                candidates = chunk.get("candidates", [])
                if not candidates:
                    continue
                parts = candidates[0].get("content", {}).get("parts", [])
                for part in parts:
                    text = part.get("text", "")
                    if text:
                        yield text
            if prompt_tokens or completion_tokens:
                self._last_usage = TokenUsage(
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
                )


class LocalOpenAILLM(ILLM):
    """Local OpenAI-compatible adapter for self-hosted LLMs (Ollama, LM Studio, vLLM, LocalAI)."""

    DEFAULT_BASE_URL = "http://localhost:11434/v1"
    DEFAULT_MODEL = "llama3.1:8b"

    def __init__(
        self,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
        api_key: Secret | None = None,
        is_visitor_key: bool = True,
    ) -> None:
        raw_url = (base_url or "").strip() or self.DEFAULT_BASE_URL
        if not raw_url.endswith("/v1") and not raw_url.endswith("/v1/"):
            raw_url = raw_url.rstrip("/") + "/v1"
        self._base_url = raw_url.rstrip("/")
        self._model = (model or "").strip() or self.DEFAULT_MODEL
        self._api_key = api_key
        self._is_visitor_key = is_visitor_key
        # Configured with loopback/local LLM egress permission enabled
        self._http_client = SecureHttpClient.create_async_client(allow_local_llm=True)

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def generate_stream(
        self,
        prompt: str,
        api_key: Secret | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Stream generated response tokens from a local OpenAI-compatible endpoint."""
        active_model = model or self._model
        key_val = api_key or self._api_key
        auth_header = (
            f"Bearer {key_val.reveal()}"
            if (key_val and key_val.reveal())
            else "Bearer ollama"
        )

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "User-Agent": "ProvenanceRAG/1.0 (Local)",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Local engines (Ollama, LM Studio) do not reliably support stream_options
        payload = {
            "model": active_model,
            "messages": messages,
            "max_tokens": DEFAULT_OUTPUT_TOKENS,
            "temperature": temperature if temperature is not None else DEFAULT_TEMPERATURE,
            "stream": True,
        }

        # Endpoints to attempt: primary base URL + host.docker.internal fallback if running inside container
        endpoints = [f"{self._base_url}/chat/completions"]
        if "localhost" in self._base_url:
            endpoints.append(self._base_url.replace("localhost", "host.docker.internal") + "/chat/completions")
        elif "127.0.0.1" in self._base_url:
            endpoints.append(self._base_url.replace("127.0.0.1", "host.docker.internal") + "/chat/completions")

        usage_sink: list[TokenUsage] = []
        last_error = None

        for endpoint in endpoints:
            try:
                print(f"\033[96m[RAG TRACE]\033[0m Calling Local LLM ({active_model}) at {endpoint} ...")
                async with self._http_client.stream(
                    "POST",
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=60.0,
                ) as response:
                    if response.status_code in (401, 403):
                        raise InvalidKeyError(provider="ollama", is_visitor_key=self._is_visitor_key)
                    if response.status_code != 200:
                        err_bytes = await response.aread()
                        err_msg = err_bytes.decode("utf-8", errors="ignore")
                        print(f"\033[91m[RAG TRACE ❌ Local Model Error]\033[0m HTTP {response.status_code} from {endpoint}: {err_msg}")
                        raise ProviderUnavailableError(
                            provider="ollama", status_code=response.status_code
                        )

                    async for content in _iter_openai_sse(response, usage_sink):
                        yield content

                    if usage_sink:
                        self._last_usage = usage_sink[-1]
                    return
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_error = exc
                continue

        print(f"\033[91m[RAG TRACE ❌ Local LLM Connection Failed]\033[0m Could not connect to any of: {endpoints}. Ensure Ollama/LM Studio is running.")
        raise ProviderUnavailableError(provider="ollama", status_code=503) from last_error


_BYOK_ADAPTERS: dict[str, tuple[type[ILLM], str]] = {
    "openai": (OpenAILLM, "gpt-4o-mini"),
    "anthropic": (AnthropicLLM, "claude-3-5-haiku-20241022"),
    "groq": (GroqLLM, "llama-3.3-70b-versatile"),
    "mistral": (MistralLLM, "mistral-small-latest"),
    "gemini": (GeminiLLM, "gemini-1.5-flash-latest"),
    "ollama": (LocalOpenAILLM, "llama3.1:8b"),
    "local": (LocalOpenAILLM, "llama3.1:8b"),
    "lmstudio": (LocalOpenAILLM, "local-model"),
}


def get_llm_adapter(
    provider: str | None = None,
    api_key: Secret | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> ILLM:
    """Factory: visitor key/local model + provider + model, else owner Groq default."""
    provider_norm = (provider or "").strip().lower()
    is_local = provider_norm in ("ollama", "local", "lmstudio")

    if (api_key and bool(api_key.reveal())) or is_local:
        if not provider_norm:
            provider_norm = "openai"
        spec = _BYOK_ADAPTERS.get(provider_norm)
        if spec is None:
            supported = ", ".join(sorted(_BYOK_ADAPTERS))
            raise ValueError(
                f"Unsupported BYOK LLM provider '{provider_norm}'. Choose one of: {supported}."
            )
        adapter_cls, default_model = spec
        if is_local:
            return adapter_cls(
                base_url=base_url,
                model=(model or default_model).strip() or default_model,
                api_key=api_key,
                is_visitor_key=True,
            )
        return adapter_cls(
            api_key=api_key,
            model=(model or default_model).strip() or default_model,
            is_visitor_key=True,
        )

    return GroqLLM(is_visitor_key=False)
