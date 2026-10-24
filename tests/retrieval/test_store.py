"""Unit tests for Qdrant vector store and scope isolation."""

from qdrant_client import QdrantClient

from src.ingest.chunking.models import ChildChunk
from src.retrieval.sparse import SparseVector
from src.retrieval.store import QdrantVectorStore


def test_qdrant_store_scope_isolation():
    """Verify strict scope isolation between different user sessions and demo corpus."""
    client = QdrantClient(location=":memory:")
    store = QdrantVectorStore(client=client, collection_name="test_isolation")

    chunk_a = ChildChunk(
        chunk_id="c_alpha",
        doc_id="doc_alpha",
        parent_id="p_alpha",
        breadcrumb="Doc Alpha",
        display_text="Alpha private confidential revenue data.",
        embedding_text="[Doc Alpha]\n\nAlpha private confidential revenue data.",
        child_tokens=10,
        chunk_index=0,
        page=1,
        content_hash="hash_a",
    )

    chunk_b = ChildChunk(
        chunk_id="c_beta",
        doc_id="doc_beta",
        parent_id="p_beta",
        breadcrumb="Doc Beta",
        display_text="Beta user confidential contracts.",
        embedding_text="[Doc Beta]\n\nBeta user confidential contracts.",
        child_tokens=10,
        chunk_index=0,
        page=1,
        content_hash="hash_b",
    )

    chunk_demo = ChildChunk(
        chunk_id="c_demo",
        doc_id="doc_demo",
        parent_id="p_demo",
        breadcrumb="Demo Public",
        display_text="Public annual report available to all.",
        embedding_text="[Demo Public]\n\nPublic annual report available to all.",
        child_tokens=10,
        chunk_index=0,
        page=1,
        content_hash="hash_demo",
    )

    # 1024-dim dummy vectors
    vec_a = [1.0] + [0.0] * 1023
    vec_b = [0.0, 1.0] + [0.0] * 1022
    vec_demo = [0.0, 0.0, 1.0] + [0.0] * 1021

    sparse_dummy = SparseVector(indices=[1, 2], values=[0.5, 0.8])

    # Upsert with different scopes
    store.upsert_chunks([chunk_a], [vec_a], [sparse_dummy], scope="session_alpha")
    store.upsert_chunks([chunk_b], [vec_b], [sparse_dummy], scope="session_beta")
    store.upsert_chunks([chunk_demo], [vec_demo], [sparse_dummy], scope="demo")

    # Search as session_alpha
    results_alpha = store.hybrid_search(
        dense_query=vec_a,
        sparse_query=sparse_dummy,
        scope="session_alpha",
        limit=10,
    )

    returned_ids_alpha = [r["chunk_id"] for r in results_alpha]
    assert "c_alpha" in returned_ids_alpha
    assert "c_demo" in returned_ids_alpha
    # CRITICAL: session_beta chunk MUST NEVER be returned!
    assert "c_beta" not in returned_ids_alpha


def test_qdrant_store_deletion():
    """Verify deleting by scope cleans up associated points."""
    client = QdrantClient(location=":memory:")
    store = QdrantVectorStore(client=client, collection_name="test_delete")

    chunk = ChildChunk(
        chunk_id="c_temp",
        doc_id="doc_temp",
        parent_id="p_temp",
        breadcrumb="Temp",
        display_text="Temporary text.",
        embedding_text="Temporary text.",
        child_tokens=5,
        chunk_index=0,
        page=1,
        content_hash="hash_t",
    )
    vec = [0.1] * 1024
    sparse_vec = SparseVector(indices=[1], values=[1.0])

    store.upsert_chunks([chunk], [vec], [sparse_vec], scope="session_temp")
    results = store.hybrid_search(dense_query=vec, sparse_query=sparse_vec, scope="session_temp")
    assert len(results) == 1

    # Delete scope
    store.delete_by_scope("session_temp")
    results_after = store.hybrid_search(dense_query=vec, sparse_query=sparse_vec, scope="session_temp")
    assert len(results_after) == 0
