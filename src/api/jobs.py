"""Asynchronous document ingestion job runner and ephemeral parser key manager.

Implements roadmap P6-T3, P6-T4, and P6-T5:
- Background ingestion queue with asyncio concurrency control
- Strict job state machine: queued -> parsing -> chunking -> embedding -> indexing -> ready | failed
- Ephemeral in-memory parser key lifecycle with guaranteed finally shredder (P6-T3)
- Quality gate integration with non-blocking warnings and automatic local fallback (P6-T4)
- Global file-hash parse caching (P6-T5)
- Partial vector rollback on failure / cancellation
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import tempfile
import time
import uuid
from pathlib import Path

import pymupdf

from src.ingest.chunking.hybrid_chunker import HybridChunker
from src.ingest.chunking.models import ChildChunk, ChunkingConfig, ParentChunk
from src.ingest.parsers.local_pymupdf import LocalPyMuPDFParser, extract_raw_reference_text
from src.ingest.parsers.quality_gate import QualityGateResult, evaluate_quality_gate
from src.ingest.parsers.registry import default_parser_registry
from src.ingest.parsers.router import FallbackParserRouter, ParseExecutionResult, RequestContext
from src.ingest.parsers.selection import canonical_parser_label
from src.ingest.parsers.structured_doc import StructuredDoc
from src.retrieval.embed import CohereEmbedder
from src.retrieval.sparse import LocalSparseVectorizer, SparseVector
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.security.credit_config import (
    GLOBAL_PARSE_CACHE_PARSER,
    GLOBAL_PARSE_CACHE_VERSION,
    PARSE_CACHE_TTL_SECONDS,
)
from src.security.errors import (
    InvalidKeyError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.security.secret import Secret
from src.api.observability import record_job_status
from src.storage.db import DatabaseManager

logger = logging.getLogger("provenance_rag.api.jobs")

# Max concurrent heavy background ingestion pipelines
DEFAULT_MAX_CONCURRENCY = 2
# Extra jobs allowed to wait on the semaphore before the API returns 429
DEFAULT_MAX_QUEUED = 2
# Wall-clock timeout for a single ingest (matches frontend INGEST_TIMEOUT_MS)
DEFAULT_JOB_TIMEOUT_SECONDS = 8 * 60


class JobRunner:
    """Coordinates async document ingestion, secret shredding, and failure recovery."""

    def __init__(
        self,
        db: DatabaseManager,
        store: QdrantVectorStore,
        cfg: OwnerConfig,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
    ) -> None:
        self.db = db
        self.store = store
        self.cfg = cfg
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_concurrency = max_concurrency
        self._max_queued = DEFAULT_MAX_QUEUED
        self._job_timeout_seconds = job_timeout_seconds
        self.chunker = HybridChunker(ChunkingConfig())
        self.embedder = CohereEmbedder(cfg.cohere_api_key)
        self.sparse_vectorizer = LocalSparseVectorizer()
        self.local_parser = LocalPyMuPDFParser()
        self.router = FallbackParserRouter(db=self.db, cfg=self.cfg)
        # Strong refs so asyncio does not GC in-flight ingest tasks (event loop
        # only keeps weak references to tasks created via asyncio.create_task).
        self._tasks: set[asyncio.Task[None]] = set()

    def spawn_ingestion_pipeline(
        self,
        job_id: str,
        session_id: str,
        filename: str,
        file_bytes: bytes,
        parser_name: str,
        parser_key: str | None = None,
        allow_fallback: bool = True,
        client_ip: str = "unknown",
    ) -> asyncio.Task[None]:
        """Schedule ingestion and retain a strong reference until it finishes."""
        task = asyncio.create_task(
            self.run_ingestion_pipeline(
                job_id=job_id,
                session_id=session_id,
                filename=filename,
                file_bytes=file_bytes,
                parser_name=parser_name,
                parser_key=parser_key,
                allow_fallback=allow_fallback,
                client_ip=client_ip,
            ),
            name=f"ingest-{job_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def run_ingestion_pipeline(
        self,
        job_id: str,
        session_id: str,
        filename: str,
        file_bytes: bytes,
        parser_name: str,
        parser_key: str | None = None,
        allow_fallback: bool = True,
        client_ip: str = "unknown",
    ) -> None:
        """Run complete ingestion pipeline in background under concurrency semaphore."""
        async with self._semaphore:
            try:
                await asyncio.wait_for(
                    self._execute_pipeline(
                        job_id=job_id,
                        session_id=session_id,
                        filename=filename,
                        file_bytes=file_bytes,
                        parser_name=parser_name,
                        parser_key=parser_key,
                        allow_fallback=allow_fallback,
                        client_ip=client_ip,
                    ),
                    timeout=self._job_timeout_seconds,
                )
            except TimeoutError:
                logger.error(f"Ingestion timed out [{job_id}] after {self._job_timeout_seconds}s")
                self._mark_job_failed(
                    job_id,
                    session_id,
                    "Ingestion timed out. Partial index data was removed. Please retry.",
                )
            except asyncio.CancelledError:
                logger.warning(f"Ingestion cancelled [{job_id}]")
                self._mark_job_failed(
                    job_id,
                    session_id,
                    "Ingestion was cancelled. Partial index data was removed. Please retry.",
                )
                raise

    async def _execute_pipeline(
        self,
        job_id: str,
        session_id: str,
        filename: str,
        file_bytes: bytes,
        parser_name: str,
        parser_key: str | None = None,
        allow_fallback: bool = True,
        client_ip: str = "unknown",
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
            content_hash = hashlib.sha256(file_bytes).hexdigest()

            # -----------------------------------------------------------------
            # Step 1: Check global file-hash parse cache
            # -----------------------------------------------------------------
            structured_doc: StructuredDoc | None = None
            parser_used = parser_name
            cached_blob = self.db.get_parse_cache(
                content_hash=content_hash,
                parser=GLOBAL_PARSE_CACHE_PARSER,
                parser_version=GLOBAL_PARSE_CACHE_VERSION,
                max_age_seconds=PARSE_CACHE_TTL_SECONDS,
            )
            if cached_blob:
                try:
                    cached_dict = json.loads(cached_blob)
                    cached_doc = cached_dict.get("doc") or cached_dict
                    structured_doc = StructuredDoc(**cached_doc)
                    parser_used = canonical_parser_label(
                        cached_dict.get("parser_label")
                        or structured_doc.parser_used
                        or parser_name
                    )
                    logger.info(f"Parse cache hit [{job_id}] for hash={content_hash[:8]}")
                except Exception as exc:
                    logger.warning(f"Failed to deserialize cached parse blob: {exc}")
                    structured_doc = None

            # -----------------------------------------------------------------
            # Step 2: Parse Document (owner auto waterfall or explicit parser)
            # -----------------------------------------------------------------
            if not structured_doc:
                parse_result = await self._parse_with_fallback(
                    pdf_path=temp_pdf_path,
                    parser_name=parser_name,
                    parser_secret=parser_secret,
                    allow_fallback=allow_fallback,
                    job_id=job_id,
                    pdf_bytes=file_bytes,
                    session_id=session_id,
                    client_ip=client_ip,
                )
                structured_doc = parse_result.structured_doc
                parser_used = canonical_parser_label(
                    parse_result.parser_label or structured_doc.parser_used or parser_name
                )
                logger.info(
                    f"Parse complete [{job_id}]: parser={parser_used} "
                    f"trail={parse_result.fallback_trail} charged={parse_result.credits_charged}"
                )

                # Store in session-scoped parse cache (never includes keys)
                try:
                    self.db.set_parse_cache(
                        content_hash=content_hash,
                        parser=GLOBAL_PARSE_CACHE_PARSER,
                        parser_version=GLOBAL_PARSE_CACHE_VERSION,
                        raw_result_blob=json.dumps(
                            {
                                "doc": structured_doc.model_dump(),
                                "parser_label": parser_used,
                                "degraded": parser_used.startswith("local"),
                            }
                        ),
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

            chunk_result = await asyncio.to_thread(self.chunker.chunk, structured_doc)
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

            # Generate sparse BM25 vectors locally ($0) off the event loop
            sparse_vectors = await asyncio.to_thread(
                self.sparse_vectorizer.vectorize_batch, embedding_texts
            )

            # -----------------------------------------------------------------
            # Step 6: Indexing into Qdrant & SQLite (sync I/O off the event loop
            # so job polling stays responsive while vectors are upserted)
            # -----------------------------------------------------------------
            self.db.update_job(job_id, status="indexing")

            await asyncio.to_thread(
                self._persist_vectors_and_metadata,
                session_id=session_id,
                doc_id=doc_id,
                filename=filename,
                structured_doc=structured_doc,
                parents=parents,
                children=children,
                dense_vectors=dense_vectors,
                sparse_vectors=sparse_vectors,
                parser_used=parser_used,
                quality_flags_str=quality_flags_str,
                content_hash=content_hash,
            )

            # Mark job ready!
            self.db.update_job(
                job_id=job_id,
                status="ready",
                pages=structured_doc.page_count,
                chunks=len(children),
                quality_flags=quality_flags_str,
                doc_id=doc_id,
            )
            record_job_status("ready")
            logger.info(
                f"Ingestion succeeded [{job_id}]: doc_id={doc_id} pages={structured_doc.page_count} chunks={len(children)}"
            )

        except asyncio.CancelledError:
            logger.warning(f"Ingestion cancelled during execute [{job_id}]")
            self._rollback_partial(doc_id, session_id)
            self.db.update_job(
                job_id=job_id,
                status="failed",
                error_message="Ingestion was cancelled or timed out. Partial index data was removed. Please retry.",
                doc_id=doc_id,
            )
            raise

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
            record_job_status("failed")

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
        pdf_bytes: bytes | None = None,
        session_id: str = "default",
        client_ip: str = "unknown",
    ) -> ParseExecutionResult:
        """Parse via the owner waterfall (auto) or an explicit parser, with local floor."""
        if pdf_bytes is not None and (allow_fallback or parser_name == "auto"):
            # auto is always owner-paid: never attach a visitor parser key to every provider.
            owner_waterfall = parser_name == "auto"
            visitor_key = None if owner_waterfall else parser_secret
            ctx = RequestContext(
                session_id=session_id,
                client_ip=client_ip or "unknown",
                sha=hashlib.sha256(pdf_bytes).hexdigest(),
                byok=bool(visitor_key and visitor_key.reveal()),
                parser_secret=visitor_key,
            )
            return await self.router.parse_with_fallback(
                pdf_path=pdf_path,
                pdf_bytes=pdf_bytes,
                ctx=ctx,
                preferred_parser=parser_name,
            )

        parser = default_parser_registry.get(parser_name)

        try:
            doc = await parser.parse(pdf_path, api_key=parser_secret)
            if allow_fallback and parser_name != "local_pymupdf" and len(doc.blocks) == 0:
                logger.warning(
                    f"Cloud parser '{parser_name}' produced 0 blocks. Falling back to local PyMuPDF [{job_id}]."
                )
                local_doc = await self.local_parser.parse(pdf_path)
                return ParseExecutionResult(
                    structured_doc=local_doc,
                    parser_label="local_pymupdf",
                    degraded=True,
                    fallback_trail=[(parser_name, "empty"), ("local_pymupdf", "ok")],
                )
            return ParseExecutionResult(
                structured_doc=doc,
                parser_label=parser_name,
                degraded=parser_name == "local_pymupdf",
            )

        except (InvalidKeyError, QuotaExhaustedError) as exc:
            raise exc

        except Exception as exc:
            if allow_fallback and parser_name != "local_pymupdf":
                logger.warning(
                    f"Parser '{parser_name}' failed with {exc}. Falling back to local PyMuPDF [{job_id}]."
                )
                local_doc = await self.local_parser.parse(pdf_path)
                return ParseExecutionResult(
                    structured_doc=local_doc,
                    parser_label="local_pymupdf",
                    degraded=True,
                    fallback_trail=[(parser_name, type(exc).__name__), ("local_pymupdf", "ok")],
                )
            raise exc

    def _persist_vectors_and_metadata(
        self,
        session_id: str,
        doc_id: str,
        filename: str,
        structured_doc: StructuredDoc,
        parents: list[ParentChunk],
        children: list[ChildChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[SparseVector],
        parser_used: str,
        quality_flags_str: str | None,
        content_hash: str,
    ) -> None:
        """Blocking Qdrant upsert + SQLite writes. Always run via asyncio.to_thread."""
        self.db.insert_parents(parents=parents, session_id=session_id)
        self.store.upsert(
            chunks=children,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            scope=session_id,
            doc_metadata={
                "title": structured_doc.title or filename,
                "parser_used": parser_used,
                "parser_version": "1.0",
                "page_count": structured_doc.page_count,
            },
        )
        self.db.insert_document(
            doc_id=doc_id,
            session_id=session_id,
            title=structured_doc.title or filename,
            content_hash=content_hash,
            page_count=structured_doc.page_count,
            parser_used=parser_used,
            parser_version="1.0",
            quality_flags=quality_flags_str,
            filename=filename,
        )
        self.db.record_document_ingestion(
            session_id=session_id,
            pages=structured_doc.page_count,
            chunks=len(children),
        )
        today_str = time.strftime("%Y-%m-%d")
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usage_daily (date, chunks_embedded, rerank_calls, owner_llm_tokens, jobs)
                VALUES (?, ?, 0, 0, 0)
                ON CONFLICT(date) DO UPDATE SET
                    chunks_embedded = chunks_embedded + excluded.chunks_embedded
                """,
                (today_str, len(children)),
            )
            conn.commit()

    def _rollback_partial(self, doc_id: str, session_id: str) -> None:
        """Delete any partial vectors/SQL rows for a failed or cancelled job."""
        try:
            self.store.delete_by_doc(doc_id)
        except Exception as rollback_exc:
            logger.warning(f"Vector rollback error for {doc_id}: {rollback_exc}")
        try:
            self.db.delete_document(doc_id, session_id)
        except Exception as rollback_exc:
            logger.warning(f"SQL rollback error for {doc_id}: {rollback_exc}")

    def _mark_job_failed(self, job_id: str, session_id: str, message: str) -> None:
        job = self.db.get_job(job_id, session_id=session_id) or {}
        if job.get("status") in {"ready", "failed"}:
            return
        doc_id = job.get("doc_id")
        if doc_id:
            self._rollback_partial(doc_id, session_id)
        self.db.update_job(job_id=job_id, status="failed", error_message=message, doc_id=doc_id)
        record_job_status("failed")

    @property
    def inflight_count(self) -> int:
        return len(self._tasks)

    def can_accept_job(self) -> bool:
        """Reject new uploads once running + queued ingest tasks fill the buffer."""
        return self.inflight_count < (self._max_concurrency + self._max_queued)

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
        if isinstance(exc, ProviderTimeoutError):
            return (
                f"{exc.provider} timed out. The document was not indexed. "
                "Please retry; visitor keys are never retried automatically."
            )
        if isinstance(exc, ProviderUnavailableError):
            if exc.provider.lower() == "cohere":
                return "Search embeddings are unavailable. The document was not indexed. Please retry later."
            return f"{exc.provider} is unavailable. The document was not indexed. Please retry later."
        if isinstance(exc, TimeoutError):
            return str(exc) or "Ingestion timed out while indexing vectors. Please retry."
        return f"Ingestion error: {exc}"
