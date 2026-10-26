"""Cohere Rerank API adapter with egress safety and graceful fallback.

Implements the IReranker interface according to architecture spec §4.4, §5 & §7.
Reranks hybrid search candidates using Cohere's two-stage rerank models (e.g. rerank-v3.5),
enforces owner caps via usage callbacks, and falls back gracefully to hybrid search order
if Cohere experiences transient outages or timeouts.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from src.interfaces import IReranker
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

COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"
DEFAULT_RERANK_MODEL = "rerank-v3.5"
DEFAULT_TOP_N = 5
RERANK_TIMEOUT_SECONDS = 5.0
MAX_RERANK_RETRIES = 1
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_RESET_TIMEOUT = 60.0


class CohereReranker(IReranker):
    """Production reranker adapter for Cohere with resilience and graceful fallback."""

    def __init__(
        self,
        api_key: Secret | None = None,
        model_name: str | None = None,
        usage_callback: Callable[[int], None] | None = None,
        timeout: float = RERANK_TIMEOUT_SECONDS,
    ) -> None:
        cfg = OwnerConfig.from_env()
        self._api_key = api_key if api_key is not None else cfg.cohere_api_key
        self._model_name = model_name or cfg.cohere_rerank_model or DEFAULT_RERANK_MODEL
        self._usage_callback = usage_callback
        self._timeout = timeout
        self._http_client = SecureHttpClient.create_async_client()

        # Circuit breaker state
        self._failure_count: int = 0
        self._circuit_open_until: float = 0.0

    @property
    def model_name(self) -> str:
        return self._model_name

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = DEFAULT_TOP_N,
    ) -> list[dict[str, Any]]:
        """Rerank candidate document texts against a query.

        Args:
            query: User's search query or question.
            documents: List of candidate texts (typically chunk embedding_text).
            top_n: Number of top results to return (default 5).

        Returns:
            List of dicts containing:
                - 'index': original integer index in the documents list
                - 'text': candidate text
                - 'relevance_score': float score [0.0 - 1.0]
                - 'is_fallback': bool indicating if hybrid fallback was used
        """
        if not documents:
            return []

        if len(documents) <= 1:
            return [
                {
                    "index": 0,
                    "text": documents[0],
                    "relevance_score": 1.0,
                    "is_fallback": False,
                }
            ]

        # Circuit breaker check: if circuit is open, trigger fallback immediately
        now = time.time()
        if now < self._circuit_open_until:
            wait_seconds = int(self._circuit_open_until - now)
            logger.warning(
                f"Cohere Rerank circuit breaker OPEN (retry in {wait_seconds}s). "
                "Falling back to hybrid order."
            )
            return self._build_fallback_results(documents, top_n)

        # Missing or invalid owner key check
        if not self._api_key or not self._api_key.reveal():
            logger.warning("Cohere API key missing for reranker. Falling back to hybrid order.")
            return self._build_fallback_results(documents, top_n)

        try:
            results = await self._call_cohere_rerank(query, documents, top_n)
            # Successful call resets circuit breaker
            self._failure_count = 0
            self._circuit_open_until = 0.0

            # Increment owner usage counter
            if self._usage_callback:
                try:
                    self._usage_callback(1)
                except Exception as exc:
                    logger.warning(f"Error executing reranker usage callback: {exc}")

            return results

        except (InvalidKeyError, QuotaExhaustedError) as auth_exc:
            logger.error(f"Cohere Rerank authentication/quota error ({auth_exc}). Falling back.")
            return self._build_fallback_results(documents, top_n)
        except Exception as exc:
            self._failure_count += 1
            if self._failure_count >= CIRCUIT_BREAKER_THRESHOLD:
                self._circuit_open_until = time.time() + CIRCUIT_BREAKER_RESET_TIMEOUT
                logger.error(
                    f"Cohere Rerank circuit breaker TRIPPED! Open for {CIRCUIT_BREAKER_RESET_TIMEOUT}s."
                )

            logger.warning(f"Cohere Rerank call failed ({exc}). Falling back to hybrid order.")
            return self._build_fallback_results(documents, top_n)

    async def _call_cohere_rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[dict[str, Any]]:
        """Call Cohere v2 rerank endpoint with 1 transient retry."""
        headers = {
            "Authorization": f"Bearer {self._api_key.reveal()}",
            "Content-Type": "application/json",
            "User-Agent": "ProvenanceRAG/1.0",
        }

        payload: dict[str, Any] = {
            "model": self._model_name,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
        }

        last_error: Exception | None = None

        for attempt in range(MAX_RERANK_RETRIES + 1):
            try:
                response = await self._http_client.post(
                    COHERE_RERANK_URL,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    scored_items = data.get("results", [])
                    results: list[dict[str, Any]] = []

                    for item in scored_items:
                        orig_idx = item["index"]
                        score = float(item["relevance_score"])
                        results.append(
                            {
                                "index": orig_idx,
                                "text": documents[orig_idx],
                                "relevance_score": score,
                                "is_fallback": False,
                            }
                        )
                    return results

                elif response.status_code in (401, 403):
                    raise InvalidKeyError(provider="cohere", is_visitor_key=False)
                elif response.status_code == 429:
                    if attempt == MAX_RERANK_RETRIES:
                        raise RateLimitedError(provider="cohere", is_visitor_key=False)
                    await asyncio.sleep(0.5)
                else:
                    raise ProviderUnavailableError(
                        provider="cohere",
                        status_code=response.status_code,
                    )

            except (InvalidKeyError, QuotaExhaustedError):
                raise
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RERANK_RETRIES:
                    await asyncio.sleep(0.5)

        raise ProviderUnavailableError(
            provider="cohere",
            status_code=500,
        ) from last_error

    def _build_fallback_results(self, documents: list[str], top_n: int) -> list[dict[str, Any]]:
        """Preserve original hybrid search ordering when reranker is unavailable."""
        return [
            {
                "index": idx,
                "text": text,
                "relevance_score": 0.0,
                "is_fallback": True,
            }
            for idx, text in enumerate(documents[:top_n])
        ]
