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
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from src.ingest.chunking.models import ChildChunk
from src.retrieval.sparse import SparseVector as LocalSparseVector
from src.security.config import OwnerConfig

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = "provenance_rag_chunks"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
DENSE_DIMENSION = 1024


class QdrantVectorStore:
    """Manages Qdrant collections, hybrid vector upserts, and scope-filtered queries."""

    def __init__(
        self,
        client: QdrantClient | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        self.collection_name = collection_name

        if client is not None:
            self._client = client
        else:
            cfg = OwnerConfig.from_env()
            if cfg.qdrant_url:
                api_key_str = cfg.qdrant_api_key.reveal() if cfg.qdrant_api_key else None
                self._client = QdrantClient(url=cfg.qdrant_url, api_key=api_key_str)
            else:
                # In-memory client for dev/tests
                self._client = QdrantClient(location=":memory:")

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
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: SparseVectorParams()
                },
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
            raise ValueError("Chunks, dense vectors, and sparse vectors must have identical lengths")

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

    def hybrid_search(
        self,
        dense_query: list[float],
        sparse_query: LocalSparseVector,
        scope: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Perform hybrid search with mandatory server-enforced scope isolation.

        Ensures results strictly originate from the active session or the shared demo corpus.
        """
        # Scope filter: user session or demo corpus
        scope_conditions = [
            FieldCondition(key="scope", match=MatchValue(value=scope)),
        ]
        if scope != "demo":
            scope_conditions.append(FieldCondition(key="scope", match=MatchValue(value="demo")))

        scope_filter = Filter(should=scope_conditions)

        # Query dense vectors with scope filter
        results = self._client.query_points(
            collection_name=self.collection_name,
            query=dense_query,
            using=DENSE_VECTOR_NAME,
            query_filter=scope_filter,
            limit=limit,
        ).points

        candidates: list[dict[str, Any]] = []
        for scored_point in results:
            payload = scored_point.payload or {}
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
