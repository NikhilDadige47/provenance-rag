"""Composable retrieval-strategy definitions for the four-way ablation."""

from __future__ import annotations

from eval.models import AblationConfig

ABLATION_CONFIGS: list[AblationConfig] = [
    AblationConfig(
        name="1_simple_chunking",
        description="Simple Chunking (Fixed-size Segments, Dense Vector Search, No Rerank)",
        chunker="simple",
        use_dense=True,
        use_sparse=False,
        use_heading_fusion=False,
        use_cohere_rerank=False,
        use_window_expansion=False,
    ),
    AblationConfig(
        name="2_semantic_chunking",
        description="Semantic Chunking (Structure & Heading Aware, Dense Vector Search, No Rerank)",
        chunker="semantic",
        use_dense=True,
        use_sparse=False,
        use_heading_fusion=True,
        use_cohere_rerank=False,
        use_window_expansion=False,
    ),
    AblationConfig(
        name="3_hybrid_search",
        description="Hybrid Search (Semantic Chunks + Dense Vector + BM25 Sparse, No Rerank)",
        chunker="semantic",
        use_dense=True,
        use_sparse=True,
        use_heading_fusion=True,
        use_cohere_rerank=False,
        use_window_expansion=False,
    ),
    AblationConfig(
        name="4_reranking",
        description="Reranking (Semantic Chunks + Hybrid Search + Lexical/Cohere Rerank + Parent Expansion)",
        chunker="semantic",
        use_dense=True,
        use_sparse=True,
        use_heading_fusion=True,
        use_cohere_rerank=True,
        use_window_expansion=True,
    ),
]


# Production Qdrant `scope=demo` is semantic-chunked. Simple chunking needs its own
# index, so live eval only runs the three strategies that share that store.
LIVE_ABLATION_CONFIGS: list[AblationConfig] = [
    config for config in ABLATION_CONFIGS if config.chunker == "semantic"
]


def config_by_name(name: str) -> AblationConfig:
    for config in ABLATION_CONFIGS:
        if config.name == name:
            return config
    raise KeyError(f"Unknown ablation config: {name}")
