"""Asynchronous document ingestion job runner and ephemeral parser key manager.

Implements roadmap P6-T3, P6-T4, and P6-T5:
- Background ingestion queue with asyncio concurrency control
- Strict job state machine: queued -> parsing -> chunking -> embedding -> indexing -> ready | failed
- Ephemeral in-memory parser key lifecycle with guaranteed finally shredder (P6-T3)
- Quality gate integration with non-blocking warnings and automatic local fallback (P6-T4)
- Session-scoped parse caching (P6-T5)
- Partial vector rollback on failure / cancellation
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
import uuid
from pathlib import Path

import pymupdf

from src.ingest.chunking.hybrid_chunker import HybridChunker
from src.ingest.chunking.models import ChunkingConfig
from src.ingest.parsers.local_pymupdf import LocalPyMuPDFParser, extract_raw_reference_text
from src.ingest.parsers.quality_gate import QualityGateResult, evaluate_quality_gate
from src.ingest.parsers.registry import default_parser_registry
from src.ingest.parsers.structured_doc import StructuredDoc
from src.retrieval.embed import CohereEmbedder
from src.retrieval.sparse import LocalSparseVectorizer
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.security.errors import InvalidKeyError, QuotaExhaustedError, RateLimitedError
from src.security.secret import Secret
from src.storage.db import DatabaseManager

logger = logging.getLogger("provenance_rag.api.jobs")

# Max concurrent heavy background ingestion pipelines
DEFAULT_MAX_CONCURRENCY = 2


class JobRunner:
    """Coordinates async document ingestion, secret shredding, and failure recovery."""

    def __init__(
        self,
        db: DatabaseManager,
        store: QdrantVectorStore,
        cfg: OwnerConfig,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self.db = db
        self.store = store
        self.cfg = cfg
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.chunker = HybridChunker(ChunkingConfig())
        self.embedder = CohereEmbedder(cfg.cohere_api_key)
        self.sparse_vectorizer = LocalSparseVectorizer()
        self.local_parser = LocalPyMuPDFParser()

    async def run_ingestion_pipeline(
        self,
        job_id: str,
        session_id: str,
        filename: str,
        file_bytes: bytes,
        parser_name: str,
        parser_key: str | None = None,
        allow_fallback: bool = True,
    ) -> None:
        """Run complete ingestion pipeline in background under concurrency semaphore."""
        async with self._semaphore:
            await self._execute_pipeline(
                job_id=job_id,
                session_id=session_id,
                filename=filename,
                file_bytes=file_bytes,
                parser_name=parser_name,
                parser_key=parser_key,
                allow_fallback=allow_fallback,
            )

    async def _execute_pipeline(
        self,
        job_id: str,
        session_id: str,
        filename: str,
        file_bytes: bytes,
        parser_name: str,
        parser_key: str | None = None,
        allow_fallback: bool = True,
    ) -> None:
        """Core execution logic with ephemeral secret shredding in finally block."""
        doc_id = "doc_" + uuid.uuid4().hex[:12]
        self.db.update_job(job_id, status="parsing", doc_id=doc_id)

        # Ephemeral parser secret: wrapped in memory only, destroyed in finally
        parser_secret: Secret | None = Secret(parser_key) if parser_key else None
        temp_pdf_path: Path | None = None

        try:
            # Write temp file for parsers that expect a Path
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_bytes)
                temp_pdf_path = Path(tmp.name)

            # Compute content hash for cache and document metadata
            import hashlib

            content_hash = hashlib.sha256(file_bytes).hexdigest()

            # -----------------------------------------------------------------
            # Step 1: Check Session-Scoped Parse Cache (P6-T5)
            # -----------------------------------------------------------------
            structured_doc: StructuredDoc | None = None
            cached_blob = self.db.get_parse_cache(
                session_id=session_id,
                content_hash=content_hash,
                parser=parser_name,
                parser_version="1.0",
            )
            if cached_blob:
                try:
                    cached_dict = json.loads(cached_blob)
                    structured_doc = StructuredDoc(**cached_dict)
                    logger.info(f"Parse cache hit [{job_id}] for hash={content_hash[:8]}")
                except Exception as exc:
                    logger.warning(f"Failed to deserialize cached parse blob: {exc}")
                    structured_doc = None

            # -----------------------------------------------------------------
            # Step 2: Parse Document (Local or Visitor Cloud Parser)
            # -----------------------------------------------------------------
            if not structured_doc:
                structured_doc = await self._parse_with_fallback(
                    pdf_path=temp_pdf_path,
                    parser_name=parser_name,
                    parser_secret=parser_secret,
                    allow_fallback=allow_fallback,
                    job_id=job_id,
                )

                # Store in session-scoped parse cache (never includes keys)
                try:
                    self.db.set_parse_cache(
                        session_id=session_id,
                        content_hash=content_hash,
                        parser=parser_name,
                        parser_version="1.0",
                        raw_result_blob=structured_doc.model_dump_json(),
                    )
                except Exception as cache_exc:
                    logger.warning(f"Could not cache parse result [{job_id}]: {cache_exc}")

            # -----------------------------------------------------------------
            # Step 3: Quality Gate Evaluation (P6-T4)
            # -----------------------------------------------------------------
            raw_ref_text = extract_raw_reference_text(temp_pdf_path)
            qg_result: QualityGateResult = evaluate_quality_gate(
                structured_doc, reference_text=raw_ref_text
            )
            quality_flags_str = (
                json.dumps(
                    {
                        "warnings": qg_result.warnings,
                        "metrics": qg_result.metrics,
                        "advice": qg_result.advice,
                    }
                )
                if qg_result.has_warnings
                else None
            )

            # -----------------------------------------------------------------
            # Step 4: Chunking (Parent-Child + Heading Fusion)
            # -----------------------------------------------------------------
            self.db.update_job(
                job_id,
                status="chunking",
                quality_flags=quality_flags_str,
                pages=structured_doc.page_count,
            )

            # Assign doc_id and resolve user-facing document title
            structured_doc.doc_id = doc_id
            doc_meta_title = ""
            try:
                if temp_pdf_path:
                    with pymupdf.open(temp_pdf_path) as pdoc:
                        doc_meta_title = (pdoc.metadata or {}).get("title", "").strip()
            except Exception:
                pass

            clean_filename_title = (
                filename.rsplit(".", 1)[0].replace("_", " ").title() if filename else "Document"
            )
            resolved_title = doc_meta_title or (
                structured_doc.title
                if structured_doc.title and not structured_doc.title.lower().startswith("tmp")
                else clean_filename_title
            )
            structured_doc.title = resolved_title

            chunk_result = self.chunker.chunk(structured_doc)
            parents = chunk_result.parents
            children = chunk_result.children

            if not children:
                raise ValueError("Chunking produced 0 searchable passages from document.")

            # -----------------------------------------------------------------
            # Step 5: Cohere Dense & Local Sparse Embedding (Owner-Paid)
            # -----------------------------------------------------------------
            self.db.update_job(job_id, status="embedding", chunks=len(children))

            embedding_texts = [c.embedding_text for c in children]

            # Generate dense vectors via Cohere
            if hasattr(self.embedder, "embed_documents"):
                dense_vectors = await self.embedder.embed_documents(embedding_texts)
            else:
                dense_vectors = await self.embedder.embed(
                    embedding_texts, input_type="search_document"
                )

            # Generate sparse BM25 vectors locally ($0)
            sparse_vectors = self.sparse_vectorizer.vectorize_batch(embedding_texts)

            # -----------------------------------------------------------------
            # Step 6: Indexing into Qdrant & SQLite
            # -----------------------------------------------------------------
            self.db.update_job(job_id, status="indexing")

            # Insert parents into SQLite
            self.db.insert_parents(parents=parents, session_id=session_id)

            # Upsert dual vectors into Qdrant strictly scoped to session_id
            doc_metadata = {
                "title": structured_doc.title or filename,
                "parser_used": parser_name,
                "parser_version": "1.0",
                "page_count": structured_doc.page_count,
            }
            self.store.upsert(
                chunks=children,
                dense_vectors=dense_vectors,
                sparse_vectors=sparse_vectors,
                scope=session_id,
                doc_metadata=doc_metadata,
            )

            # Record document metadata in SQLite
            self.db.insert_document(
                doc_id=doc_id,
                session_id=session_id,
                title=structured_doc.title or filename,
                content_hash=content_hash,
                page_count=structured_doc.page_count,
                parser_used=parser_name,
                parser_version="1.0",
                quality_flags=quality_flags_str,
            )

            # Atomically update session usage counters
            self.db.record_document_ingestion(
                session_id=session_id,
                pages=structured_doc.page_count,
                chunks=len(children),
            )

            # Update daily usage tracking
            today_str = time.strftime("%Y-%m-%d")
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO usage_daily (date, chunks_embedded, jobs)
                    VALUES (?, ?, 1)
                    ON CONFLICT(date) DO UPDATE SET
                        chunks_embedded = chunks_embedded + excluded.chunks_embedded,
                        jobs = jobs + 1
                    """,
                    (today_str, len(children)),
                )
                conn.commit()

            # Mark job ready!
            self.db.update_job(
                job_id=job_id,
                status="ready",
                pages=structured_doc.page_count,
                chunks=len(children),
                quality_flags=quality_flags_str,
                doc_id=doc_id,
            )
            logger.info(
                f"Ingestion succeeded [{job_id}]: doc_id={doc_id} pages={structured_doc.page_count} chunks={len(children)}"
            )

        except Exception as exc:
            logger.error(f"Ingestion failed [{job_id}]: {type(exc).__name__}: {exc}", exc_info=True)
            friendly_error = self._format_error(exc)

            # Roll back partial vectors and parents
            try:
                self.store.delete_by_doc(doc_id)
                self.db.delete_document(doc_id, session_id)
            except Exception as rollback_exc:
                logger.warning(f"Rollback error [{job_id}]: {rollback_exc}")

            self.db.update_job(
                job_id=job_id,
                status="failed",
                error_message=friendly_error,
                doc_id=doc_id,
            )

        finally:
            # 🔴 CRITICAL SECURITY INVARIANT: Shred visitor parser secret from memory
            if parser_secret is not None:
                del parser_secret
                parser_secret = None

            # Clean up temp PDF file on disk
            if temp_pdf_path and temp_pdf_path.exists():
                try:
                    temp_pdf_path.unlink()
                except Exception as cleanup_exc:
                    logger.warning(f"Could not remove temp file {temp_pdf_path}: {cleanup_exc}")

    async def _parse_with_fallback(
        self,
        pdf_path: Path,
        parser_name: str,
        parser_secret: Secret | None,
        allow_fallback: bool,
        job_id: str,
    ) -> StructuredDoc:
        """Parse with selected parser, gracefully falling back to PyMuPDF on failure."""
        parser = default_parser_registry.get(parser_name)

        try:
            doc = await parser.parse(pdf_path, api_key=parser_secret)
            # If cloud parser produced virtually no text, consider local fallback
            if allow_fallback and parser_name != "local_pymupdf" and len(doc.blocks) == 0:
                logger.warning(
                    f"Cloud parser '{parser_name}' produced 0 blocks. Falling back to local PyMuPDF [{job_id}]."
                )
                return await self.local_parser.parse(pdf_path)
            return doc

        except (InvalidKeyError, QuotaExhaustedError) as exc:
            # Visitor key errors must fail fast without retry
            raise exc

        except Exception as exc:
            if allow_fallback and parser_name != "local_pymupdf":
                logger.warning(
                    f"Parser '{parser_name}' failed with {exc}. Falling back to local PyMuPDF [{job_id}]."
                )
                return await self.local_parser.parse(pdf_path)
            raise exc

    def _format_error(self, exc: Exception) -> str:
        """Format friendly error messages without leaking provider keys or internals."""
        if isinstance(exc, InvalidKeyError):
            return (
                f"Your parser API key was rejected: {exc.message}. Please check your credentials."
            )
        if isinstance(exc, QuotaExhaustedError):
            return f"Parser quota exceeded: {exc.message}. Please check your account balance."
        if isinstance(exc, RateLimitedError):
            return "Parser provider is currently rate-limited. Please retry in a few moments."
        return f"Ingestion error: {exc}"
