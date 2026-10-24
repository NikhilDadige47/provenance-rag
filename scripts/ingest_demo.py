"""Offline demo corpus ingestion script for Tier A (Zero-Key Demo).

Ingests public domain PDF documents from demo_corpus/ into SQLite and Qdrant
under scope = 'demo' using the owner's pinned embedding model according to spec P3-T9.
"""

import asyncio
import logging
from pathlib import Path

from src.ingest.chunking.hybrid_chunker import HybridChunker
from src.ingest.parsers.cleanup import fix_hyphenation, remove_repeated_headers_and_footers
from src.ingest.parsers.local_pymupdf import LocalPyMuPDFParser
from src.ingest.parsers.quality_gate import QualityGate
from src.retrieval.embed import CohereEmbedder
from src.retrieval.sparse import LocalSparseVectorizer
from src.retrieval.store import QdrantVectorStore
from src.storage.db import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("demo_ingest")

DEMO_CORPUS_DIR = Path("demo_corpus")


async def ingest_demo_document(
    pdf_path: Path,
    chunker: HybridChunker,
    sparse_vectorizer: LocalSparseVectorizer,
    embedder: CohereEmbedder | None,
    store: QdrantVectorStore,
    db: DatabaseManager,
) -> int:
    """Ingest a single demo document into scope='demo'."""
    logger.info(f"Processing demo document: {pdf_path.name}")

    # 1. Parse locally
    parser = LocalPyMuPDFParser()
    doc = await parser.parse(pdf_path)

    # 2. Cleanup
    doc = remove_repeated_headers_and_footers(doc)
    doc = fix_hyphenation(doc)

    # 3. Quality Gate
    gate = QualityGate()
    ref_text = parser.extract_raw_reference_text(pdf_path)
    q_res = gate.evaluate(doc, ref_text)
    if q_res.has_warnings:
        logger.warning(f"Quality gate warnings on {pdf_path.name}: {q_res.warning_messages}")

    # 4. Chunking
    chunk_res = chunker.chunk(doc)
    logger.info(
        f"Generated {len(chunk_res.parents)} parents and {len(chunk_res.children)} children."
    )

    # 5. Store parents in SQL
    db.insert_parents(chunk_res.parents, session_id="demo")

    # 6. Compute sparse vectors locally ($0 cost)
    texts_to_embed = [c.embedding_text for c in chunk_res.children]
    sparse_vectors = sparse_vectorizer.vectorize_batch(texts_to_embed)

    # 7. Compute dense vectors
    if embedder:
        try:
            dense_vectors = await embedder.embed(texts_to_embed, input_type="search_document")
        except Exception as exc:
            logger.warning(f"Cohere embedding failed ({exc}). Using fallback vectors for local demo.")
            dense_vectors = [[0.01] * 1024 for _ in chunk_res.children]
    else:
        dense_vectors = [[0.01] * 1024 for _ in chunk_res.children]

    # 8. Upsert to Qdrant under scope = "demo"
    count = store.upsert_chunks(
        chunks=chunk_res.children,
        dense_vectors=dense_vectors,
        sparse_vectors=sparse_vectors,
        scope="demo",
        doc_metadata={"title": doc.title, "parser_used": "local_pymupdf"},
    )
    logger.info(f"Successfully upserted {count} chunks into Qdrant (scope='demo').")
    return count


async def main() -> None:
    """Run ingestion over all demo PDFs."""
    chunker = HybridChunker()
    sparse_vectorizer = LocalSparseVectorizer()
    store = QdrantVectorStore()
    db = DatabaseManager()

    # Optional embedder (falls back gracefully if owner key is not set)
    try:
        embedder = CohereEmbedder()
    except Exception:
        embedder = None

    pdf_files = list(DEMO_CORPUS_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.info(f"No PDF files found in {DEMO_CORPUS_DIR}. Place demo PDFs here for offline ingestion.")
        return

    total = 0
    for pdf in pdf_files:
        total += await ingest_demo_document(
            pdf_path=pdf,
            chunker=chunker,
            sparse_vectorizer=sparse_vectorizer,
            embedder=embedder,
            store=store,
            db=db,
        )

    logger.info(f"Demo corpus ingestion completed: {total} total chunks indexed under scope='demo'.")


if __name__ == "__main__":
    asyncio.run(main())
