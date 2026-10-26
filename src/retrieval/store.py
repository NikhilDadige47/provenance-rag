"""Qdrant vector store adapter supporting hybrid search and scope isolation.

Implements native dense + sparse vector indexing in Qdrant with payload indexing on
'scope' and 'doc_id' according to architecture spec §4.4, §6, and §7.
"""

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from src.ingest.chunking.models import ChildChunk
from src.interfaces import IVectorStore
from src.retrieval.sparse import SparseVector as LocalSparseVector
from src.security.config import OwnerConfig

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = "provenance_rag_chunks"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
DENSE_DIMENSION = 1024


class QdrantVectorStore(IVectorStore):
    """Manages Qdrant collections, hybrid vector upserts, and scope-filtered queries."""

    def __init__(
        self,
        client: QdrantClient | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        cfg: OwnerConfig | None = None,
    ) -> None:
        self.collection_name = collection_name

        if client is not None:
            self._client = client
        else:
            config = cfg or OwnerConfig.from_env()
            if config.qdrant_url == ":memory:":
                self._client = QdrantClient(":memory:")
            elif config.qdrant_url:
                try:
                    api_key_str = config.qdrant_api_key.reveal() if config.qdrant_api_key else None
                    remote_client = QdrantClient(
                        url=config.qdrant_url, api_key=api_key_str, timeout=2.0
                    )
                    # Verify connectivity
                    remote_client.get_collections()
                    self._client = remote_client
                except Exception as exc:
                    logger.warning(
                        f"Could not connect to Qdrant at {config.qdrant_url} ({exc}). "
                        "Falling back to local embedded Qdrant (./qdrant_storage)."
                    )
                    self._client = QdrantClient(path="./qdrant_storage")
            else:
                self._client = QdrantClient(path="./qdrant_storage")

        self.ensure_collection()

    def ensure_collection(self) -> None:
        """Create the hybrid collection and payload indexes if they do not exist."""
        collections = self._client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            logger.info(f"Creating Qdrant collection: {self.collection_name}")
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: VectorParams(
                        size=DENSE_DIMENSION,
                        distance=Distance.COSINE,
                    )
                },
                sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
            )

            # Create payload indexes on 'scope' and 'doc_id' for fast isolated filtering
            self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name="scope",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name="doc_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )

    def upsert_chunks(
        self,
        chunks: list[ChildChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[LocalSparseVector],
        scope: str,
        doc_metadata: dict[str, Any] | None = None,
    ) -> int:
        """Idempotently upsert children chunks with dual vectors and scope tagging.

        Returns number of points upserted.
        """
        if not chunks:
            return 0

        if len(chunks) != len(dense_vectors) or len(chunks) != len(sparse_vectors):
            raise ValueError(
                "Chunks, dense vectors, and sparse vectors must have identical lengths"
            )

        meta = doc_metadata or {}
        points: list[PointStruct] = []

        for _idx, (chunk, dense_vec, sparse_vec) in enumerate(
            zip(chunks, dense_vectors, sparse_vectors, strict=False)
        ):
            payload = {
                "chunk_id": chunk.chunk_id,
                "scope": scope,
                "doc_id": chunk.doc_id,
                "title": meta.get("title", ""),
                "breadcrumb": chunk.breadcrumb,
                "page": chunk.page,
                "bbox": chunk.bbox,
                "chunk_type": chunk.chunk_type,
                "display_text": chunk.display_text,
                "embedding_text": chunk.embedding_text,
                "child_tokens": chunk.child_tokens,
                "parent_id": chunk.parent_id,
                "chunk_index": chunk.chunk_index,
                "prev_chunk_id": chunk.prev_chunk_id,
                "next_chunk_id": chunk.next_chunk_id,
                "content_hash": chunk.content_hash,
                "parser_used": meta.get("parser_used", "unknown"),
                "parser_version": meta.get("parser_version", "1.0"),
                "embed_provider": "cohere",
                "embed_model": "embed-english-v3.0",
                "embedding_version": "emb-v1",
                "chunking_version": "hybrid-v1",
            }

            point_id = abs(hash(chunk.chunk_id)) % (2**63 - 1)

            points.append(
                PointStruct(
                    id=point_id,
                    vector={
                        DENSE_VECTOR_NAME: dense_vec,
                        SPARSE_VECTOR_NAME: SparseVector(
                            indices=sparse_vec.indices,
                            values=sparse_vec.values,
                        ),
                    },
                    payload=payload,
                )
            )

        self._client.upsert(collection_name=self.collection_name, points=points)
        return len(points)

    # Alias for API consistency
    upsert = upsert_chunks

    def hybrid_search(
        self,
        dense_query: list[float],
        sparse_query: LocalSparseVector | None = None,
        scope: str = "demo",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Perform hybrid search with mandatory server-enforced scope isolation.

        Combines dense and sparse vectors via Reciprocal Rank Fusion (RRF).
        Ensures results strictly originate from the active session or the shared demo corpus.
        """
        # Scope filter: user session or demo corpus
        scope_conditions = [
            FieldCondition(key="scope", match=MatchValue(value=scope)),
        ]
        if scope != "demo":
            scope_conditions.append(FieldCondition(key="scope", match=MatchValue(value="demo")))

        scope_filter = Filter(should=scope_conditions)

        # True hybrid RRF fusion if sparse query has active terms
        has_sparse = (
            sparse_query is not None and bool(sparse_query.indices) and bool(sparse_query.values)
        )

        if has_sparse:
            prefetch = [
                Prefetch(
                    query=dense_query,
                    using=DENSE_VECTOR_NAME,
                    filter=scope_filter,
                    limit=limit * 2,
                ),
                Prefetch(
                    query=SparseVector(
                        indices=sparse_query.indices,
                        values=sparse_query.values,
                    ),
                    using=SPARSE_VECTOR_NAME,
                    filter=scope_filter,
                    limit=limit * 2,
                ),
            ]
            results = self._client.query_points(
                collection_name=self.collection_name,
                prefetch=prefetch,
                query=FusionQuery(fusion=Fusion.RRF),
                limit=limit,
            ).points
        else:
            # Dense fallback if no sparse terms
            results = self._client.query_points(
                collection_name=self.collection_name,
                query=dense_query,
                using=DENSE_VECTOR_NAME,
                query_filter=scope_filter,
                limit=limit,
            ).points

        # Query-time embedding_version validation (Roadmap P3-T8)
        configured_version = OwnerConfig.from_env().embedding_version
        candidates: list[dict[str, Any]] = []

        for scored_point in results:
            payload = scored_point.payload or {}
            point_version = payload.get("embedding_version")
            if point_version and point_version != configured_version:
                raise ValueError(
                    f"Embedding version mismatch: indexed chunk has version '{point_version}', "
                    f"configured server version is '{configured_version}'. Please re-index the collection."
                )

            candidates.append(
                {
                    "chunk_id": payload.get("chunk_id"),
                    "score": scored_point.score,
                    "payload": payload,
                }
            )

        return candidates

    def delete_by_scope(self, scope: str) -> None:
        """Delete all points associated with a specific session scope."""
        self._client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="scope", match=MatchValue(value=scope))]
            ),
        )

    def delete_by_doc(self, doc_id: str) -> None:
        """Delete all points associated with a specific document ID."""
        self._client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )
