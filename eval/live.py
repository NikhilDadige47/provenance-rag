"""Live evaluation against the permanent Qdrant demo index.

The demo corpus is parsed with local PyMuPDF, semantically chunked, and
Cohere-embedded once under scope='demo'. Strategies 2-4 reuse those vectors.
Strategy 1 (simple chunking) cannot run here — the stored chunks are different.
"""

from __future__ import annotations

from eval.evaluate import Evaluator
from eval.models import AblationConfig
from src.generation.prompt import PromptBuilder
from src.retrieval.embed import CohereEmbedder
from src.retrieval.expansion import ContextExpander
from src.retrieval.rerank import CohereReranker
from src.retrieval.search import HybridSearchPipeline
from src.retrieval.store import QdrantVectorStore
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager


class LiveIndexError(RuntimeError):
    """Raised when live eval cannot use the production demo index."""


def has_usable_cohere_key(cfg: OwnerConfig | None = None) -> bool:
    """True when a non-placeholder Cohere key is configured."""
    config = cfg or OwnerConfig.from_env()
    key = config.cohere_api_key.reveal() if config.cohere_api_key else ""
    lowered = key.strip().lower()
    return bool(lowered) and "placeholder" not in lowered


def ensure_semantic_live_config(config: AblationConfig) -> None:
    """Reject simple-chunking configs; those vectors are not in scope=demo."""
    if config.chunker == "simple":
        raise LiveIndexError(
            "Simple chunking cannot search the production demo index. "
            "scope=demo is ingested with HybridChunker (semantic). "
            "Run strategy 1 with the offline fixture harness."
        )


class LiveEvalHarness:
    """Evaluator factory backed by Qdrant scope=demo and Cohere Embed/Rerank."""

    def __init__(self, cfg: OwnerConfig | None = None) -> None:
        self.cfg = cfg or OwnerConfig.from_env()
        if not has_usable_cohere_key(self.cfg):
            raise LiveIndexError(
                "Live eval requires a real COHERE_API_KEY (not the placeholder). "
                "Ingest the demo PDFs with scripts/ingest_demo.py first."
            )
        self.db = DatabaseManager()
        embedder = CohereEmbedder(api_key=self.cfg)
        reranker = CohereReranker(api_key=self.cfg)
        searcher = HybridSearchPipeline(
            embedder=embedder,
            store=QdrantVectorStore(cfg=self.cfg),
            reranker=reranker,
        )
        self._evaluator = Evaluator(
            searcher=searcher,
            reranker=reranker,
            expander=ContextExpander(db=self.db),
            prompt_builder=PromptBuilder(),
            db=self.db,
            cfg=self.cfg,
        )

    def evaluator(self, config: AblationConfig) -> Evaluator:
        ensure_semantic_live_config(config)
        return self._evaluator
