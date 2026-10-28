"""Collection-aware lexical reranker for offline evaluation (no API calls)."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from eval.text_utils import STOPWORDS, tokenize
from src.interfaces import IReranker

OOD_SCORE_CAP = 0.15
OOD_UNSEEN_RATIO = 0.30


class LexicalReranker(IReranker):
    """IDF-weighted query-term coverage over candidate documents.

    Distinctive out-of-corpus terms (high IDF, df=0) drag the score down, which
    is what makes the not-found gate fire on trick questions without Cohere.
    """

    def __init__(
        self,
        document_frequency: dict[str, int] | None = None,
        n_docs: int = 0,
    ) -> None:
        self.document_frequency = document_frequency or {}
        self.n_docs = n_docs

    @property
    def model_name(self) -> str:
        return "lexical-idf-v1"

    def _idf(self, token: str, fallback_df: dict[str, int], fallback_n: int) -> float:
        n_docs = self.n_docs or fallback_n
        df = self.document_frequency.get(token, fallback_df.get(token, 0))
        return math.log((n_docs + 1) / (df + 1)) + 1.0

    async def rerank(
        self, query: str, documents: list[str], top_n: int = 5
    ) -> list[dict[str, Any]]:
        query_tokens = [token for token in tokenize(query) if token not in STOPWORDS]
        if not documents:
            return []

        candidate_df: dict[str, int] = Counter()
        doc_token_sets = []
        for document in documents:
            tokens = set(tokenize(document))
            doc_token_sets.append(tokens)
            for token in tokens:
                candidate_df[token] += 1

        in_vocab = [
            token for token in query_tokens if self.document_frequency.get(token, 0) > 0
        ]
        unseen = [
            token
            for token in query_tokens
            if len(token) > 3 and self.document_frequency.get(token, 0) == 0
        ]
        unseen_ratio = len(unseen) / len(query_tokens) if query_tokens else 0.0

        scored: list[tuple[int, float, str]] = []
        for idx, (document, doc_tokens) in enumerate(zip(documents, doc_token_sets, strict=True)):
            scored_tokens = in_vocab or query_tokens
            if not scored_tokens:
                score = 0.0
            else:
                weight_total = 0.0
                weight_hit = 0.0
                for token in scored_tokens:
                    idf = self._idf(token, candidate_df, len(documents))
                    weight_total += idf
                    if token in doc_tokens:
                        weight_hit += idf
                score = weight_hit / weight_total if weight_total else 0.0
            if unseen_ratio > OOD_UNSEEN_RATIO:
                score = min(score, OOD_SCORE_CAP)
            scored.append((idx, score, document))

        scored.sort(key=lambda row: (-row[1], row[0]))
        selected = scored[: min(top_n, len(scored))]
        return [
            {
                "index": idx,
                "text": text,
                "relevance_score": round(score, 4),
                "is_fallback": False,
            }
            for idx, score, text in selected
        ]
