"""Cohere Embed API adapter with egress safety and bounded retries.

Implements the IEmbedder interface according to architecture spec §5 & §7.
Pins the embedding model and version, enforces search_document vs search_query types,
and tracks chunk usage against owner financial caps.
"""

import asyncio
import logging
import time
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

# Constants
COHERE_EMBED_URL = "https://api.cohere.com/v2/embed"
DEFAULT_MODEL = "embed-english-v3.0"
EMBEDDING_DIMENSION = 1024
MAX_BATCH_SIZE = 96
MAX_RETRIES = 3
INITIAL_BACKOFF = 0.5
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_RESET_TIMEOUT = 60.0


class CohereEmbedder(IEmbedder):
    """Production embedder adapter for Cohere v3 embeddings with circuit breaker."""

    def __init__(
        self,
        api_key: Secret | OwnerConfig | None = None,
        model_name: str = DEFAULT_MODEL,
        dimension: int = EMBEDDING_DIMENSION,
        usage_callback: Callable[[int], None] | None = None,
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
        # Circuit breaker state
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
        """Compute dense vector embeddings for input texts in batches.

        Args:
            texts: List of text strings to embed.
            input_type: 'search_document' for chunks, 'search_query' for search queries.

        Returns:
            List of float vector embeddings (1024 dimensions each).
        """
        if not texts:
            return []

        # Circuit breaker check
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

        # Split into batches respecting Cohere's 96 items limit
        for i in range(0, len(texts), MAX_BATCH_SIZE):
            batch = texts[i : i + MAX_BATCH_SIZE]
            batch_vectors = await self._embed_batch_with_retry(batch, input_type)
            all_vectors.extend(batch_vectors)

            # Record usage against owner spend meter if callback provided
            if self._usage_callback:
                try:
                    self._usage_callback(len(batch))
                except Exception as exc:
                    logger.warning(f"Error executing embedder usage callback: {exc}")

        return all_vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Alias for embed(texts, input_type='search_document')."""
        return await self.embed(texts, input_type="search_document")

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

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self._http_client.post(
                    COHERE_EMBED_URL,
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    # Cohere v2 format: data["embeddings"]["float"]
                    if "embeddings" in data and "float" in data["embeddings"]:
                        vectors = data["embeddings"]["float"]
                    elif "embeddings" in data and isinstance(data["embeddings"], list):
                        vectors = data["embeddings"]
                    else:
                        raise ProviderUnavailableError(provider="cohere")

                    # Verify vector dimensions
                    if vectors and len(vectors[0]) != self._dimension:
                        raise ProviderUnavailableError(
                            provider="cohere",
                            status_code=500,
                        )

                    # Success resets failure count
                    self._failure_count = 0
                    self._circuit_open_until = 0.0
                    return vectors

                elif response.status_code in (401, 403):
                    raise InvalidKeyError(provider="cohere", is_visitor_key=False)
                elif response.status_code == 429:
                    # Rate limit - honor backoff if attempts remaining
                    if attempt == MAX_RETRIES:
                        raise RateLimitedError(provider="cohere", is_visitor_key=False)
                    logger.warning(
                        f"Cohere rate limit (429). Retrying in {backoff}s (attempt {attempt})..."
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                else:
                    raise ProviderUnavailableError(
                        provider="cohere",
                        status_code=response.status_code,
                    )

            except (InvalidKeyError, QuotaExhaustedError):
                raise
            except Exception as exc:
                last_exception = exc
                if attempt == MAX_RETRIES:
                    break
                await asyncio.sleep(backoff)
                backoff *= 2.0

        self._failure_count += 1
        if self._failure_count >= CIRCUIT_BREAKER_THRESHOLD:
            self._circuit_open_until = time.time() + CIRCUIT_BREAKER_RESET_TIMEOUT
            logger.error(
                f"Cohere circuit breaker TRIPPED! Open for {CIRCUIT_BREAKER_RESET_TIMEOUT}s."
            )

        logger.error(f"Failed to embed batch after {MAX_RETRIES} attempts: {last_exception}")
        raise ProviderUnavailableError(
            provider="cohere",
            status_code=500,
        )
