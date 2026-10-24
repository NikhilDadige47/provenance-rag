"""Offline demo corpus ingestion script for Tier A (Zero-Key Demo).

Ingests public domain PDF documents from demo_corpus/ into SQLite and Qdrant
under scope = 'demo' using the owner's pinned embedding model according to spec P3-T9.
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is in sys.path when script is executed directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ingest.chunking.hybrid_chunker import HybridChunker
from src.ingest.parsers.local_pymupdf import LocalPyMuPDFParser, extract_raw_reference_text
from src.ingest.parsers.quality_gate import evaluate_parse_quality
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

    # 1. Parse locally using PyMuPDF (no key required)
    parser = LocalPyMuPDFParser()
    doc = await parser.parse(pdf_path)

    # 2. Quality Gate check
    ref_text = extract_raw_reference_text(pdf_path)
    q_res = evaluate_parse_quality(doc, ref_text)
    if q_res.has_warnings:
        logger.warning(f"Quality gate warnings on {pdf_path.name}: {q_res.warnings}")

    # 3. Hybrid Chunking (structure + recursive + parent-child)
    chunk_res = chunker.chunk(doc)
    logger.info(
        f"Generated {len(chunk_res.parents)} parents and {len(chunk_res.children)} children for {doc.title}."
    )

    # 4. Store parents and document in SQL under scope = 'demo'
    db.insert_parents(chunk_res.parents, session_id="demo")
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO documents (
                doc_id, session_id, title, content_hash, page_count, parser_used, parser_version,
                chunking_version, embedding_version, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.doc_id,
                "demo",
                doc.title,
                chunk_res.children[0].content_hash if chunk_res.children else "demo_hash",
                doc.page_count,
                "local_pymupdf",
                doc.parser_version,
                chunk_res.chunking_version,
                "emb-v1",
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()

    # 5. Compute sparse vectors locally ($0 cost)
    texts_to_embed = [c.embedding_text for c in chunk_res.children]
    sparse_vectors = sparse_vectorizer.vectorize_batch(texts_to_embed)

    # 6. Compute dense vectors (Cohere Embed or fallback dummy vector in offline dev)
    if embedder:
        try:
            dense_vectors = await embedder.embed(texts_to_embed, input_type="search_document")
        except Exception as exc:
            logger.warning(f"Cohere embedding failed ({exc}). Using fallback vectors for local demo.")
            dense_vectors = [[0.01] * 1024 for _ in chunk_res.children]
    else:
        dense_vectors = [[0.01] * 1024 for _ in chunk_res.children]

    # 7. Upsert to Qdrant under scope = "demo"
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
