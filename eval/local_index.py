"""In-memory dual-vector index used by offline ablation and the CI gate."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from eval.local_embedder import HashingEmbedder
from eval.local_rerank import LexicalReranker
from eval.text_utils import tokenize
from src.ingest.chunking.models import ChildChunk, ChunkingResult, ParentChunk
from src.retrieval.search import RetrievedChunk, SearchResult
from src.retrieval.sparse import LocalSparseVectorizer, SparseVector

RRF_K = 60
DEFAULT_NOT_FOUND_THRESHOLD = 0.25


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _sparse_dot(left: SparseVector, right: SparseVector) -> float:
    right_map = dict(zip(right.indices, right.values, strict=False))
    return sum(
        value * right_map[idx]
        for idx, value in zip(left.indices, left.values, strict=False)
        if idx in right_map
    )


def _rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    return scores


@dataclass
class IndexedRecord:
    chunk: ChildChunk
    parent: ParentChunk | None
    dense: list[float]
    sparse: SparseVector


@dataclass
class LocalEvalIndex:
    """Hashed dense + BM25-style sparse index over a single chunking scheme."""

    records: list[IndexedRecord]
    embedder: HashingEmbedder
    sparse_vectorizer: LocalSparseVectorizer
    document_frequency: dict[str, int] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        results: list[ChunkingResult],
        embedder: HashingEmbedder | None = None,
        sparse_vectorizer: LocalSparseVectorizer | None = None,
    ) -> LocalEvalIndex:
        embedder = embedder or HashingEmbedder()
        sparse_vectorizer = sparse_vectorizer or LocalSparseVectorizer()
        parents = {parent.parent_id: parent for result in results for parent in result.parents}
        records: list[IndexedRecord] = []
        df: dict[str, int] = defaultdict(int)

        for result in results:
            for child in result.children:
                tokens = set(tokenize(child.embedding_text))
                for token in tokens:
                    df[token] += 1
                records.append(
                    IndexedRecord(
                        chunk=child,
                        parent=parents.get(child.parent_id),
                        dense=embedder.embed_one(child.embedding_text),
                        sparse=sparse_vectorizer.vectorize(child.embedding_text),
                    )
                )

        return cls(
            records=records,
            embedder=embedder,
            sparse_vectorizer=sparse_vectorizer,
            document_frequency=dict(df),
        )

    @property
    def children(self) -> list[ChildChunk]:
        return [record.chunk for record in self.records]

    @property
    def parents(self) -> list[ParentChunk]:
        seen: dict[str, ParentChunk] = {}
        for record in self.records:
            if record.parent is not None:
                seen[record.parent.parent_id] = record.parent
        return list(seen.values())

    def search_candidates(
        self,
        query: str,
        *,
        use_dense: bool,
        use_sparse: bool,
        limit: int,
    ) -> list[RetrievedChunk]:
        if not self.records:
            return []

        by_id = {record.chunk.chunk_id: record for record in self.records}
        dense_ranking: list[str] = []
        sparse_ranking: list[str] = []

        if use_dense:
            query_dense = self.embedder.embed_one(query)
            dense_scored = sorted(
                (
                    (_cosine(query_dense, record.dense), record.chunk.chunk_id)
                    for record in self.records
                ),
                key=lambda row: row[0],
                reverse=True,
            )
            dense_ranking = [chunk_id for _, chunk_id in dense_scored]

        if use_sparse:
            query_sparse = self.sparse_vectorizer.vectorize(query)
            sparse_scored = sorted(
                (
                    (_sparse_dot(query_sparse, record.sparse), record.chunk.chunk_id)
                    for record in self.records
                ),
                key=lambda row: row[0],
                reverse=True,
            )
            sparse_ranking = [chunk_id for _, chunk_id in sparse_scored]

        rankings = [ranking for ranking in (dense_ranking, sparse_ranking) if ranking]
        if not rankings:
            fused = {record.chunk.chunk_id: 0.0 for record in self.records}
        elif len(rankings) == 1:
            fused = {chunk_id: 1.0 / (rank + 1) for rank, chunk_id in enumerate(rankings[0])}
        else:
            fused = _rrf(rankings)

        ordered_ids = sorted(fused, key=lambda chunk_id: fused[chunk_id], reverse=True)[:limit]
        return [
            _record_to_chunk(by_id[chunk_id], score=fused[chunk_id]) for chunk_id in ordered_ids
        ]


class LocalEvalSearcher:
    """HybridSearchPipeline-compatible searcher backed by LocalEvalIndex."""

    def __init__(
        self,
        index: LocalEvalIndex,
        reranker: LexicalReranker | None = None,
        not_found_threshold: float = DEFAULT_NOT_FOUND_THRESHOLD,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
    ) -> None:
        self.index = index
        self.reranker = reranker or LexicalReranker(
            document_frequency=index.document_frequency,
            n_docs=len(index.records),
        )
        self.not_found_threshold = not_found_threshold
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    async def search(
        self,
        query: str,
        scope: str = "demo",
        limit: int = 30,
        top_n: int = 5,
        disable_rerank: bool = False,
    ) -> SearchResult:
        cleaned = query.strip()
        if not cleaned:
            return SearchResult(query=query, scope=scope, chunks=[], is_found=False, reason="empty_query")

        candidates = self.index.search_candidates(
            cleaned,
            use_dense=self.dense_weight > 0.0,
            use_sparse=self.sparse_weight > 0.0,
            limit=limit,
        )
        if not candidates:
            return SearchResult(
                query=cleaned, scope=scope, chunks=[], is_found=False, reason="no_candidates"
            )

        is_fallback = False
        if disable_rerank or self.reranker is None:
            selected = candidates[:top_n]
            is_fallback = True
        else:
            documents = [chunk.embedding_text or chunk.display_text for chunk in candidates]
            reranked = await self.reranker.rerank(cleaned, documents, top_n=top_n)
            selected = []
            for item in reranked:
                chunk = candidates[item["index"]]
                selected.append(
                    RetrievedChunk(
                        chunk_id=chunk.chunk_id,
                        doc_id=chunk.doc_id,
                        parent_id=chunk.parent_id,
                        title=chunk.title,
                        breadcrumb=chunk.breadcrumb,
                        page=chunk.page,
                        bbox=chunk.bbox,
                        display_text=chunk.display_text,
                        embedding_text=chunk.embedding_text,
                        score=float(item["relevance_score"]),
                        is_fallback_score=bool(item.get("is_fallback", False)),
                        metadata=chunk.metadata,
                    )
                )
                if item.get("is_fallback"):
                    is_fallback = True

        if not selected:
            return SearchResult(
                query=cleaned, scope=scope, chunks=[], is_found=False, reason="no_chunks_after_rerank"
            )

        best_score = selected[0].score
        if not is_fallback and best_score < self.not_found_threshold:
            return SearchResult(
                query=cleaned,
                scope=scope,
                chunks=selected,
                is_found=False,
                is_fallback=is_fallback,
                reason="below_relevance_threshold",
            )

        return SearchResult(
            query=cleaned,
            scope=scope,
            chunks=selected,
            is_found=True,
            is_fallback=is_fallback,
        )


def _record_to_chunk(record: IndexedRecord, score: float) -> RetrievedChunk:
    child = record.chunk
    return RetrievedChunk(
        chunk_id=child.chunk_id,
        doc_id=child.doc_id,
        parent_id=child.parent_id,
        title=child.breadcrumb.split(">")[0].strip() if child.breadcrumb else "",
        breadcrumb=child.breadcrumb,
        page=child.page,
        bbox=child.bbox,
        display_text=child.display_text,
        embedding_text=child.embedding_text,
        score=score,
        metadata={"parent_id": child.parent_id},
    )
