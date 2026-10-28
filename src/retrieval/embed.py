"""Cohere Embed API adapter with egress safety and bounded retries.

Rate limits (https://docs.cohere.com/docs/rate-limits):
- Embed: 2,000 inputs / minute (trial and production)
- Trial keys also cap at 1,000 API calls / month (each batch POST is one call)
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from src.interfaces import IEmbedder
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

COHERE_EMBED_URL = "https://api.cohere.com/v2/embed"
DEFAULT_MODEL = "embed-english-v3.0"
EMBEDDING_DIMENSION = 1024
MAX_BATCH_SIZE = 96
MAX_RETRIES = 3
INITIAL_BACKOFF = 0.5
DEFAULT_RATE_LIMIT_WAIT = 30.0
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_RESET_TIMEOUT = 60.0

# Official Embed cap is 2,000 inputs/min; keep 10% headroom for concurrent chat.
COHERE_EMBED_INPUTS_PER_MINUTE = 2000
DEFAULT_EMBED_INPUT_BUDGET = 1800
INPUT_WINDOW_SECONDS = 60.0


def _retry_after_seconds(response: Any, fallback: float) -> float:
    """Prefer Cohere's Retry-After header; otherwise use the configured wait."""
    raw = None
    try:
        headers = getattr(response, "headers", None) or {}
        raw = headers.get("Retry-After") or headers.get("retry-after")
    except Exception:
        raw = None
    if raw:
        try:
            return max(fallback, float(raw))
        except (TypeError, ValueError):
            pass
    return fallback


class CohereEmbedder(IEmbedder):
    """Production embedder adapter for Cohere v3 embeddings with circuit breaker."""

    def __init__(
        self,
        api_key: Secret | OwnerConfig | None = None,
        model_name: str = DEFAULT_MODEL,
        dimension: int = EMBEDDING_DIMENSION,
        usage_callback: Callable[[int], None] | None = None,
        max_inputs_per_minute: int = DEFAULT_EMBED_INPUT_BUDGET,
        min_request_gap_seconds: float = 0.0,
        rate_limit_wait_seconds: float = DEFAULT_RATE_LIMIT_WAIT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        if isinstance(api_key, OwnerConfig):
            self._api_key = api_key.cohere_api_key
        elif api_key is not None:
            self._api_key = api_key
        else:
            self._api_key = OwnerConfig.from_env().cohere_api_key
        self._model_name = model_name
        self._dimension = dimension
        self._usage_callback = usage_callback
        self._http_client = SecureHttpClient.create_async_client()
        self._max_inputs_per_minute = max(1, int(max_inputs_per_minute))
        self._min_request_gap_seconds = max(0.0, float(min_request_gap_seconds))
        self._rate_limit_wait_seconds = max(1.0, float(rate_limit_wait_seconds))
        self._max_retries = max(1, int(max_retries))
        self._input_window: deque[tuple[float, int]] = deque()
        self._last_request_at: float = 0.0
        self._failure_count: int = 0
        self._circuit_open_until: float = 0.0

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(
        self, texts: list[str], input_type: str = "search_document"
    ) -> list[list[float]]:
        """Compute dense vector embeddings for input texts in batches."""
        if not texts:
            return []

        now = time.time()
        if now < self._circuit_open_until:
            wait_seconds = int(self._circuit_open_until - now)
            logger.warning(f"Cohere circuit breaker OPEN. Retry in {wait_seconds}s.")
            raise ProviderUnavailableError(
                provider="cohere",
                status_code=503,
            )

        if not self._api_key or not self._api_key.reveal():
            raise InvalidKeyError(
                provider="cohere",
                is_visitor_key=False,
            )

        all_vectors: list[list[float]] = []
        total_batches = (len(texts) + MAX_BATCH_SIZE - 1) // MAX_BATCH_SIZE
        for batch_idx, i in enumerate(range(0, len(texts), MAX_BATCH_SIZE), start=1):
            batch = texts[i : i + MAX_BATCH_SIZE]
            await self._pace(len(batch))
            logger.info(
                "Cohere embed batch %s/%s (%s texts)",
                batch_idx,
                total_batches,
                len(batch),
            )
            batch_vectors = await self._embed_batch_with_retry(batch, input_type)
            all_vectors.extend(batch_vectors)
            sent_at = time.monotonic()
            self._last_request_at = sent_at
            self._input_window.append((sent_at, len(batch)))

            if self._usage_callback:
                try:
                    self._usage_callback(len(batch))
                except Exception as extra:
                    logger.warning(f"Error executing embedder usage callback: {extra}")

        return all_vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Alias for embed(texts, input_type='search_document')."""
        return await self.embed(texts, input_type="search_document")

    def _prune_window(self, now: float) -> int:
        while self._input_window and now - self._input_window[0][0] >= INPUT_WINDOW_SECONDS:
            self._input_window.popleft()
        return sum(count for _, count in self._input_window)

    async def _pace(self, next_inputs: int) -> None:
        """Stay under Cohere's 2,000 embed inputs/minute and optional request gap."""
        now = time.monotonic()
        if self._min_request_gap_seconds > 0 and self._last_request_at > 0:
            gap = self._min_request_gap_seconds - (now - self._last_request_at)
            if gap > 0:
                await asyncio.sleep(gap)
                now = time.monotonic()

        used = self._prune_window(now)
        if used + next_inputs <= self._max_inputs_per_minute:
            return

        overflow = used + next_inputs - self._max_inputs_per_minute
        wait = 0.0
        for ts, count in self._input_window:
            overflow -= count
            wait = INPUT_WINDOW_SECONDS - (now - ts)
            if overflow <= 0:
                break
        wait = max(wait, 0.05)
        logger.info(
            "Cohere embed budget %s/%s inputs in 60s (cap 2,000/min). Waiting %.1fs.",
            used,
            self._max_inputs_per_minute,
            wait,
        )
        await asyncio.sleep(wait)

    async def _embed_batch_with_retry(self, batch: list[str], input_type: str) -> list[list[float]]:
        """Execute a single batch embedding call with bounded exponential backoff."""
        headers = {
            "Authorization": f"Bearer {self._api_key.reveal()}",
            "Content-Type": "application/json",
            "User-Agent": "ProvenanceRAG/1.0",
        }

        payload: dict[str, Any] = {
            "model": self._model_name,
            "texts": batch,
            "input_type": input_type,
            "embedding_types": ["float"],
            "truncate": "END",
        }

        backoff = INITIAL_BACKOFF
        last_exception: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._http_client.post(
                    COHERE_EMBED_URL,
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    if "embeddings" in data and "float" in data["embeddings"]:
                        vectors = data["embeddings"]["float"]
                    elif "embeddings" in data and isinstance(data["embeddings"], list):
                        vectors = data["embeddings"]
                    else:
                        raise ProviderUnavailableError(provider="cohere")

                    if vectors and len(vectors[0]) != self._dimension:
                        raise ProviderUnavailableError(
                            provider="cohere",
                            status_code=500,
                        )

                    self._failure_count = 0
                    self._circuit_open_until = 0.0
                    return vectors

                if response.status_code in (401, 403):
                    raise InvalidKeyError(provider="cohere", is_visitor_key=False)
                if response.status_code == 429:
                    wait = _retry_after_seconds(response, self._rate_limit_wait_seconds)
                    if attempt == self._max_retries:
                        raise RateLimitedError(
                            provider="cohere",
                            is_visitor_key=False,
                            retry_after_seconds=wait,
                        )
                    logger.warning(
                        "Cohere rate limit (429). Waiting %.0fs (attempt %s/%s)...",
                        wait,
                        attempt,
                        self._max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise ProviderUnavailableError(
                    provider="cohere",
                    status_code=response.status_code,
                )

            except (InvalidKeyError, QuotaExhaustedError, RateLimitedError):
                raise
            except Exception as extra:
                last_exception = extra
                if attempt == self._max_retries:
                    break
                await asyncio.sleep(backoff)
                backoff *= 2.0

        self._failure_count += 1
        if self._failure_count >= CIRCUIT_BREAKER_THRESHOLD:
            self._circuit_open_until = time.time() + CIRCUIT_BREAKER_RESET_TIMEOUT
            logger.error(
                f"Cohere circuit breaker TRIPPED! Open for {CIRCUIT_BREAKER_RESET_TIMEOUT}s."
            )

        logger.error(
            f"Failed to embed batch after {self._max_retries} attempts: {last_exception}"
        )
        raise ProviderUnavailableError(
            provider="cohere",
            status_code=500,
        )
