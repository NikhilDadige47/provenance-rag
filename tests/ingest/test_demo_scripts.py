"""Integration test for offline demo ingestion and re-embed scripts."""

import pytest
from qdrant_client import QdrantClient

from scripts.ingest_demo import DEMO_CORPUS_DIR, ingest_demo_document
from src.ingest.chunking.hybrid_chunker import HybridChunker
from src.retrieval.sparse import LocalSparseVectorizer
from src.retrieval.store import QdrantVectorStore
from src.storage.db import DatabaseManager


@pytest.mark.asyncio
async def test_demo_corpus_ingestion_end_to_end(tmp_path):
    """Verify demo documents are successfully parsed, quality-checked, chunked, and stored."""
    db_file = tmp_path / "test_demo.db"
    db = DatabaseManager(db_path=db_file)
    client = QdrantClient(location=":memory:")
    store = QdrantVectorStore(client=client, collection_name="test_demo_collection")
    chunker = HybridChunker()
    sparse_vectorizer = LocalSparseVectorizer()

    pdf_files = list(DEMO_CORPUS_DIR.glob("*.pdf"))
    assert len(pdf_files) >= 1, "Expected at least 1 demo corpus PDF file"

    total_chunks = 0
    for pdf in pdf_files:
        count = await ingest_demo_document(
            pdf_path=pdf,
            chunker=chunker,
            sparse_vectorizer=sparse_vectorizer,
            embedder=None,  # Tests offline fallback vectors
            store=store,
            db=db,
        )
        assert count > 0
        total_chunks += count

    assert total_chunks >= 2

    # Verify SQL records
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents WHERE session_id = 'demo'")
        doc_count = cursor.fetchone()[0]
        assert doc_count == len(pdf_files)

        cursor.execute("SELECT COUNT(*) FROM parents WHERE session_id = 'demo'")
        parent_count = cursor.fetchone()[0]
        assert parent_count > 0

    # Verify Qdrant search over scope = 'demo'
    results = store.hybrid_search(
        dense_query=[0.01] * 1024,
        sparse_query=None,
        scope="demo",
        limit=5,
    )
    assert len(results) > 0
    assert results[0]["payload"]["scope"] == "demo"
