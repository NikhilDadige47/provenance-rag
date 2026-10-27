"""Hybrid retrieval orchestrator with mandatory scope isolation and not-found gate.

Implements roadmap P4-T1 & P4-T3:
- Query dense embedding with Cohere Embed (input_type='search_query')
- Query sparse encoding locally with BM25
- Qdrant hybrid search with server-enforced scope filter [session_id, 'demo']
- Cohere Rerank (top 5) with transient fallback
- Not-found threshold evaluation before LLM execution
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from src.retrieval.embed import CohereEmbedder
from src.retrieval.rerank import CohereReranker
from src.retrieval.sparse import LocalSparseVectorizer
from src.retrieval.store import QdrantVectorStore

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_LIMIT = 30
DEFAULT_RERANK_TOP_N = 5
DEFAULT_NOT_FOUND_THRESHOLD = 0.25


@dataclass
class RetrievedChunk:
    """A scored chunk retrieved and reranked for generation."""

    chunk_id: str
    doc_id: str
    parent_id: str
    title: str
    breadcrumb: str
    page: int
    bbox: list[float] | None
    display_text: str
    embedding_text: str
    score: float
    is_fallback_score: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """The outcome of hybrid retrieval and reranking."""

    query: str
    scope: str
    chunks: list[RetrievedChunk]
    is_found: bool
    is_fallback: bool = False
    reason: str | None = None


class HybridSearchPipeline:
    """Orchestrates hybrid dense+sparse search and reranking under server-enforced scope."""

    def __init__(
        self,
        embedder: CohereEmbedder | None = None,
        sparse_vectorizer: LocalSparseVectorizer | None = None,
        store: QdrantVectorStore | None = None,
        reranker: CohereReranker | None = None,
        not_found_threshold: float = DEFAULT_NOT_FOUND_THRESHOLD,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
    ) -> None:
        self.embedder = embedder or CohereEmbedder()
        self.sparse_vectorizer = sparse_vectorizer or LocalSparseVectorizer()
        self.store = store or QdrantVectorStore()
        self.reranker = reranker or CohereReranker()
        self.not_found_threshold = not_found_threshold
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    async def search(
        self,
        query: str,
        scope: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        top_n: int = DEFAULT_RERANK_TOP_N,
        disable_rerank: bool = False,
    ) -> SearchResult:
        """Execute hybrid search strictly scoped to the user session and demo corpus.

        Args:
            query: User's query string.
            scope: Server-derived session identifier.
            limit: Candidates to fetch from Qdrant before reranking.
            top_n: Final number of reranked chunks to return.
            disable_rerank: If True, bypass reranking (used for ablation tests).

        Returns:
            SearchResult with scored chunks and not-found status.
        """
        cleaned_query = query.strip()
        if not cleaned_query:
            return SearchResult(
                query=query,
                scope=scope,
                chunks=[],
                is_found=False,
                reason="empty_query",
            )

        # 1. Compute dense query embedding if dense_weight > 0
        if self.dense_weight > 0.0:
            dense_vectors = await self.embedder.embed([cleaned_query], input_type="search_query")
            dense_query = dense_vectors[0] if dense_vectors else [0.0] * self.embedder.dimension
        else:
            dense_query = [0.0] * self.embedder.dimension

        # 2. Compute local sparse vector query ($0 compute) if sparse_weight > 0
        sparse_query = (
            self.sparse_vectorizer.vectorize(cleaned_query) if self.sparse_weight > 0.0 else None
        )

        # 3. Hybrid search in Qdrant with server-enforced scope filter
        raw_candidates = self.store.hybrid_search(
            dense_query=dense_query,
            sparse_query=sparse_query,
            scope=scope,
            limit=limit,
        )

        if not raw_candidates:
            logger.info(f"No candidates found for query '{cleaned_query[:40]}' in scope '{scope}'.")
            return SearchResult(
                query=cleaned_query,
                scope=scope,
                chunks=[],
                is_found=False,
                reason="no_candidates",
            )

        # 4. Two-stage reranking with Cohere Rerank
        is_fallback = False
        if disable_rerank or not self.reranker:
            # Ablation mode: use raw hybrid search order
            selected_candidates = raw_candidates[:top_n]
            retrieved_chunks = [
                self._map_candidate_to_chunk(
                    cand, score=float(cand.get("score", 0.0)), is_fallback=True
                )
                for cand in selected_candidates
            ]
            is_fallback = True
        else:
            doc_texts = [
                c.get("payload", {}).get("embedding_text", "")
                or c.get("payload", {}).get("display_text", "")
                for c in raw_candidates
            ]
            rerank_results = await self.reranker.rerank(
                query=cleaned_query,
                documents=doc_texts,
                top_n=top_n,
            )

            retrieved_chunks = []
            for item in rerank_results:
                orig_cand = raw_candidates[item["index"]]
                score = float(item["relevance_score"])
                fallback_flag = item.get("is_fallback", False)
                if fallback_flag:
                    is_fallback = True

                chunk = self._map_candidate_to_chunk(
                    orig_cand,
                    score=score,
                    is_fallback=fallback_flag,
                )
                retrieved_chunks.append(chunk)

        # 5. Not-found evaluation gate (Roadmap P4-T3)
        # If best rerank score is below threshold and not an outage fallback, reject early
        if not retrieved_chunks:
            return SearchResult(
                query=cleaned_query,
                scope=scope,
                chunks=[],
                is_found=False,
                reason="no_chunks_after_rerank",
            )

        best_score = retrieved_chunks[0].score
        if not is_fallback and best_score < self.not_found_threshold:
            logger.info(
                f"Not-found gate triggered: best score {best_score:.3f} < threshold {self.not_found_threshold:.3f}"
            )
            return SearchResult(
                query=cleaned_query,
                scope=scope,
                chunks=retrieved_chunks,
                is_found=False,
                is_fallback=is_fallback,
                reason="below_relevance_threshold",
            )

        return SearchResult(
            query=cleaned_query,
            scope=scope,
            chunks=retrieved_chunks,
            is_found=True,
            is_fallback=is_fallback,
        )

    def _map_candidate_to_chunk(
        self, candidate: dict[str, Any], score: float, is_fallback: bool
    ) -> RetrievedChunk:
        """Map raw Qdrant scored payload to typed RetrievedChunk."""
        payload = candidate.get("payload", {})
        return RetrievedChunk(
            chunk_id=payload.get("chunk_id", ""),
            doc_id=payload.get("doc_id", ""),
            parent_id=payload.get("parent_id", ""),
            title=payload.get("title", ""),
            breadcrumb=payload.get("breadcrumb", ""),
            page=payload.get("page", 1),
            bbox=payload.get("bbox"),
            display_text=payload.get("display_text", ""),
            embedding_text=payload.get("embedding_text", ""),
            score=score,
            is_fallback_score=is_fallback,
            metadata=payload,
        )


HybridSearcher = HybridSearchPipeline
