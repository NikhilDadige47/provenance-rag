"""Re-embed script for the demo corpus when embedding_version changes.

Adheres to Roadmap P3-T8:
- Clears existing demo vectors in Qdrant (scope = 'demo')
- Clears demo parents and document metadata in SQL
- Marks active non-demo visitor sessions expired (since embedding versions must match)
- Re-ingests all documents in demo_corpus/ with current OwnerConfig embedding version
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

from scripts.ingest_demo import DEMO_CORPUS_DIR, ingest_demo_document
from src.ingest.chunking.hybrid_chunker import HybridChunker
from src.retrieval.embed import CohereEmbedder
from src.retrieval.sparse import LocalSparseVectorizer
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reembed_demo")


async def reembed_all() -> None:
    cfg = OwnerConfig.from_env()
    logger.info(f"Initiating demo re-embedding under version: {cfg.embedding_version}")

    store = QdrantVectorStore()
    db = DatabaseManager()
    chunker = HybridChunker()
    sparse_vectorizer = LocalSparseVectorizer()

    try:
        embedder = CohereEmbedder()
    except Exception:
        embedder = None

    # 1. Clear old demo corpus vectors from Qdrant
    logger.info("Purging existing demo vectors from Qdrant...")
    store.delete_by_scope("demo")

    # 2. Clear old demo parents and documents from SQLite
    logger.info("Purging demo rows from SQL...")
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM parents WHERE session_id = 'demo'")
        cursor.execute("DELETE FROM documents WHERE session_id = 'demo'")
        # Expire active sessions to force refresh on embedding version shift
        now_iso = datetime.now(UTC).isoformat()
        cursor.execute("UPDATE sessions SET expires_at = ? WHERE expires_at IS NULL OR expires_at > ?", (now_iso, now_iso))
        conn.commit()

    # 3. Re-ingest all documents in demo_corpus/
    pdf_files = list(DEMO_CORPUS_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.info(f"No PDFs found in {DEMO_CORPUS_DIR}. Place demo PDFs here to re-embed.")
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

    logger.info(f"Re-embedding complete! Total {total} chunks re-indexed under version '{cfg.embedding_version}'.")


if __name__ == "__main__":
    asyncio.run(reembed_all())
