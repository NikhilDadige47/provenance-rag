"""Offline evaluation harness: dual indexes over the golden-set fixture corpus."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from eval.corpus_fixture import build_apple_corpus
from eval.evaluate import Evaluator
from eval.local_embedder import HashingEmbedder
from eval.local_index import LocalEvalIndex, LocalEvalSearcher
from eval.local_rerank import LexicalReranker
from eval.models import AblationConfig
from src.generation.prompt import PromptBuilder
from src.ingest.chunking.hybrid_chunker import HybridChunker
from src.ingest.chunking.models import ChunkingConfig, ChunkingResult
from src.ingest.chunking.simple_chunker import SimpleChunker
from src.ingest.parsers.structured_doc import StructuredDoc
from src.retrieval.expansion import ContextExpander
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager


@dataclass
class EvalIndexBundle:
    """Simple vs semantic indexes plus a shared parent store for expansion."""

    simple: LocalEvalIndex
    semantic: LocalEvalIndex
    db: DatabaseManager

    def index_for(self, config: AblationConfig) -> LocalEvalIndex:
        return self.simple if config.chunker == "simple" else self.semantic

    def searcher_for(self, config: AblationConfig) -> LocalEvalSearcher:
        index = self.index_for(config)
        reranker = LexicalReranker(
            document_frequency=index.document_frequency,
            n_docs=len(index.records),
        )
        return LocalEvalSearcher(
            index=index,
            reranker=reranker,
            not_found_threshold=config.not_found_threshold,
            dense_weight=1.0 if config.use_dense else 0.0,
            sparse_weight=1.0 if config.use_sparse else 0.0,
        )


def _chunk_corpus(
    docs: list[StructuredDoc],
    simple: SimpleChunker,
    semantic: HybridChunker,
) -> tuple[list[ChunkingResult], list[ChunkingResult]]:
    simple_results = [simple.chunk(doc) for doc in docs]
    semantic_results = [semantic.chunk(doc) for doc in docs]
    return simple_results, semantic_results


def build_index_bundle(
    docs: list[StructuredDoc] | None = None,
    db: DatabaseManager | None = None,
) -> EvalIndexBundle:
    """Chunk the corpus twice and index both representations in memory."""
    corpus = docs or build_apple_corpus()
    if db is None:
        db_path = Path(tempfile.mkdtemp(prefix="provenance_eval_")) / "eval.db"
        database = DatabaseManager(db_path=db_path)
    else:
        database = db
    database.create_or_get_session("demo", tier="tier_a")

    simple_chunker = SimpleChunker(ChunkingConfig(use_heading_fusion=False))
    semantic_chunker = HybridChunker(ChunkingConfig(use_heading_fusion=True))
    simple_results, semantic_results = _chunk_corpus(corpus, simple_chunker, semantic_chunker)

    embedder = HashingEmbedder()
    simple_index = LocalEvalIndex.build(simple_results, embedder=embedder)
    semantic_index = LocalEvalIndex.build(semantic_results, embedder=embedder)

    database.insert_parents(simple_index.parents, session_id="demo")
    database.insert_parents(semantic_index.parents, session_id="demo")

    return EvalIndexBundle(simple=simple_index, semantic=semantic_index, db=database)


def make_evaluator(
    bundle: EvalIndexBundle,
    config: AblationConfig,
    cfg: OwnerConfig | None = None,
) -> Evaluator:
    """Wire an Evaluator to the index and flags for one ablation config."""
    searcher = bundle.searcher_for(config)
    return Evaluator(
        searcher=searcher,
        reranker=searcher.reranker,
        expander=ContextExpander(db=bundle.db),
        prompt_builder=PromptBuilder(),
        db=bundle.db,
        cfg=cfg or OwnerConfig(qdrant_url=":memory:"),
    )


class OfflineEvalHarness:
    """One-object entry point for dual-index ablation and the CI accuracy gate."""

    def __init__(self, bundle: EvalIndexBundle | None = None) -> None:
        self.bundle = bundle or build_index_bundle()

    @classmethod
    def from_fixture(cls) -> OfflineEvalHarness:
        return cls(build_index_bundle())

    def evaluator(self, config: AblationConfig) -> Evaluator:
        return make_evaluator(self.bundle, config)
