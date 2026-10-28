"""Deterministic hashing embedder for offline evaluation (no API calls)."""

from __future__ import annotations

import hashlib
import math

from eval.text_utils import tokenize
from src.interfaces import IEmbedder

DEFAULT_DIMENSION = 256


class HashingEmbedder(IEmbedder):
    """Bag-of-words hashing trick with L2-normalized dense vectors."""

    def __init__(self, dimension: int = DEFAULT_DIMENSION) -> None:
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return "hashing-bow-v1"

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(
        self, texts: list[str], input_type: str = "search_document"
    ) -> list[list[float]]:
        del input_type
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text: str) -> list[float]:
        """Project tokens into a fixed-size dense vector and L2-normalize."""
        vector = [0.0] * self._dimension
        tokens = tokenize(text)
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self._dimension
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]
