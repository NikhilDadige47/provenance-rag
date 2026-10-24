"""Local BM25 / token-frequency sparse vector generation.

Runs entirely in-process ($0 cost, no API calls) and computes sparse vectors
compatible with Qdrant's native sparse vector search according to architecture spec §4.4 & §6.
"""

import collections
import hashlib
import math
import re

# Word tokenizer for sparse representation
_TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9_]{2,}\b")


class SparseVector:
    """Sparse vector representation containing non-zero indices and weights."""

    def __init__(self, indices: list[int], values: list[float]) -> None:
        self.indices = indices
        self.values = values

    def as_dict(self) -> dict[str, list]:
        """Convert to dictionary format expected by Qdrant sparse vectors."""
        return {
            "indices": self.indices,
            "values": self.values,
        }


class LocalSparseVectorizer:
    """Local sparse vectorizer using term frequency and deterministic token hashing.

    Generates sparse vectors with positive float values and 32-bit hash indices,
    enabling hybrid keyword + semantic search in Qdrant without external dependencies.
    """

    def __init__(self, index_space: int = 2**20) -> None:
        # 1M dimension space to minimize hash collisions
        self.index_space = index_space

    def _hash_token(self, token: str) -> int:
        """Hash a token into a stable 32-bit integer index within index_space."""
        digest = hashlib.md5(token.lower().encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % self.index_space

    def vectorize(self, text: str) -> SparseVector:
        """Compute sparse term frequency vector for input text."""
        tokens = _TOKEN_PATTERN.findall(text.lower())
        if not tokens:
            return SparseVector(indices=[], values=[])

        # Frequency histogram
        counts = collections.Counter(tokens)
        total_tokens = len(tokens)

        # Map to hashed indices and sublinear TF weighting: 1 + ln(tf)
        index_weights: dict[int, float] = collections.defaultdict(float)
        for token, count in counts.items():
            idx = self._hash_token(token)
            weight = 1.0 + math.log(count)
            # Normalize by length to prevent longer chunks from dominating
            norm_weight = weight / math.sqrt(total_tokens)
            index_weights[idx] = max(index_weights[idx], float(round(norm_weight, 4)))

        sorted_items = sorted(index_weights.items(), key=lambda x: x[0])
        indices = [item[0] for item in sorted_items]
        values = [item[1] for item in sorted_items]

        return SparseVector(indices=indices, values=values)

    def vectorize_batch(self, texts: list[str]) -> list[SparseVector]:
        """Batch vectorize multiple texts."""
        return [self.vectorize(t) for t in texts]
