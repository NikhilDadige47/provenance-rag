"""Offline demo corpus ingestion script for Tier A (Zero-Key Demo).

Parser is selected by DEMO_PARSER (or --parser): local_pymupdf | llamaparse |
landingai. Visitor uploads are unchanged. Chunks are Cohere-embedded once into
Qdrant under scope='demo' for the live demo UI and live golden-set evaluation.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path when script is executed directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ingest.chunking.hybrid_chunker import HybridChunker
from src.ingest.demo_parser import (
    DEFAULT_DEMO_PARSER,
    DEMO_PARSER_CHOICES,
    DemoParserError,
    resolve_demo_parser,
)
from src.ingest.parsers.local_pymupdf import LocalPyMuPDFParser, extract_raw_reference_text
from src.ingest.parsers.quality_gate import evaluate_parse_quality
from src.interfaces import IParser
from src.retrieval.embed import CohereEmbedder
from src.retrieval.sparse import LocalSparseVectorizer
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.security.secret import Secret
from src.storage.db import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("demo_ingest")

DEMO_CORPUS_DIR = Path("demo_corpus")
DEMO_PARSER_NAME = DEFAULT_DEMO_PARSER


def list_demo_pdfs(corpus_dir: Path = DEMO_CORPUS_DIR) -> list[Path]:
    """Prefer Apple 10-Ks when present; otherwise ingest every PDF in the folder."""
    apple = sorted(corpus_dir.glob("Apple-Annual-Report-*.pdf"))
    if apple:
        return apple
    return sorted(corpus_dir.glob("*.pdf"))


async def ingest_demo_document(
    pdf_path: Path,
    chunker: HybridChunker,
    sparse_vectorizer: LocalSparseVectorizer,
    embedder: CohereEmbedder | None,
    store: QdrantVectorStore,
    db: DatabaseManager,
    require_embeddings: bool = False,
    parser: IParser | None = None,
    parser_key: Secret | None = None,
) -> int:
    """Ingest a single demo document into scope='demo'."""
    logger.info(f"Processing demo document: {pdf_path.name}")

    active_parser = parser or LocalPyMuPDFParser()
    logger.info("Parsing %s with %s", pdf_path.name, active_parser.name)
    doc = await active_parser.parse(pdf_path, api_key=parser_key)

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

    # 4. Store document then parents (parents.doc_id REFERENCES documents)
    db.create_or_get_session("demo", tier="tier_a_demo")
    db.insert_document(
        doc_id=doc.doc_id,
        session_id="demo",
        title=doc.title,
        content_hash=(
            chunk_res.children[0].content_hash if chunk_res.children else "demo_hash"
        ),
        page_count=doc.page_count,
        parser_used=active_parser.name,
        parser_version=doc.parser_version,
        chunking_version=chunk_res.chunking_version,
        filename=pdf_path.name,
    )
    db.insert_parents(chunk_res.parents, session_id="demo")

    # 5. Compute sparse vectors locally ($0 cost)
    texts_to_embed = [c.embedding_text for c in chunk_res.children]
    sparse_vectors = sparse_vectorizer.vectorize_batch(texts_to_embed)

    # 6. Compute dense vectors (Cohere Embed or fallback dummy vector in offline dev)
    if embedder:
        try:
            dense_vectors = await embedder.embed(texts_to_embed, input_type="search_document")
        except Exception as exc:
            if require_embeddings:
                raise
            logger.warning(
                f"Cohere embedding failed ({exc}). Using fallback vectors for local demo."
            )
            dense_vectors = [[0.01] * 1024 for _ in chunk_res.children]
    else:
        dense_vectors = [[0.01] * 1024 for _ in chunk_res.children]

    # 7. Upsert to Qdrant under scope = "demo"
    count = store.upsert_chunks(
        chunks=chunk_res.children,
        dense_vectors=dense_vectors,
        sparse_vectors=sparse_vectors,
        scope="demo",
        doc_metadata={"title": doc.title, "parser_used": active_parser.name},
    )
    logger.info(f"Successfully upserted {count} chunks into Qdrant (scope='demo').")
    return count


async def main() -> None:
    """Run ingestion over demo PDFs into the permanent Qdrant demo scope."""
    cli = argparse.ArgumentParser(
        description="Ingest demo PDFs into Qdrant scope=demo. Parser from DEMO_PARSER or --parser."
    )
    cli.add_argument(
        "--parser",
        choices=DEMO_PARSER_CHOICES,
        default=None,
        help="Override DEMO_PARSER for this run (local_pymupdf | llamaparse | landingai).",
    )
    cli.add_argument(
        "--require-embeddings",
        action="store_true",
        help="Fail instead of writing dummy vectors when Cohere is unavailable.",
    )
    cli.add_argument(
        "--embed-inputs-per-minute",
        type=int,
        default=1800,
        help="Cohere Embed budget (official cap is 2000 inputs/min). Default 1800 leaves headroom.",
    )
    args = cli.parse_args()

    cfg = OwnerConfig.from_env()
    try:
        demo_parser, demo_key = resolve_demo_parser(name=args.parser, cfg=cfg)
    except DemoParserError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc

    chunker = HybridChunker()
    sparse_vectorizer = LocalSparseVectorizer()
    store = QdrantVectorStore(cfg=cfg)
    db = DatabaseManager()

    try:
        embedder = CohereEmbedder(
            max_inputs_per_minute=args.embed_inputs_per_minute,
            min_request_gap_seconds=0.5,
            rate_limit_wait_seconds=30.0,
            max_retries=8,
        )
        logger.info(
            "Cohere Embed limit is 2,000 inputs/min (trial and production). "
            "Pacing to %s inputs/min; 30s wait on 429. Trial keys also cap at "
            "1,000 API calls/month.",
            args.embed_inputs_per_minute,
        )
    except Exception:
        embedder = None

    production = (cfg.app_env or "").lower() == "production"
    if (args.require_embeddings or production) and embedder is None:
        logger.error("Cohere Embed is required for demo ingest but is not configured.")
        raise SystemExit(1)

    pdf_files = list_demo_pdfs()
    if not pdf_files:
        logger.info(
            f"No PDF files found in {DEMO_CORPUS_DIR}. Place demo PDFs here for offline ingestion."
        )
        return

    logger.info(
        "Ingesting %s PDF(s) with parser=%s into Qdrant scope=demo.",
        len(pdf_files),
        demo_parser.name,
    )

    total = 0
    for pdf in pdf_files:
        total += await ingest_demo_document(
            pdf_path=pdf,
            chunker=chunker,
            sparse_vectorizer=sparse_vectorizer,
            embedder=embedder,
            store=store,
            db=db,
            require_embeddings=args.require_embeddings,
            parser=demo_parser,
            parser_key=demo_key,
        )

    logger.info(
        f"Demo corpus ingestion completed: {total} total chunks indexed under scope='demo'."
    )


if __name__ == "__main__":
    asyncio.run(main())
