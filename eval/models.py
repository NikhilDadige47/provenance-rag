"""Pydantic data models for evaluation benchmarks, metrics, and ablation studies (Phase 7)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    """Normalized response payload for LLM generation during evaluation."""

    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class EvalItem(BaseModel):
    """A single evaluation query from golden_set.jsonl."""

    id: str
    category: Literal["direct_fact", "table_numbers", "multi_section", "not_in_corpus"]
    question: str
    expected_doc: str | None = None
    expected_page: int | None = None
    expected_answer: str
    keywords: list[str] = Field(default_factory=list)
    is_not_found: bool = False


class QueryResult(BaseModel):
    """Result of running a single query through the RAG pipeline."""

    item_id: str
    question: str
    category: str
    answer: str
    not_found: bool
    sources: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: float = 0.0
    tokens_used: int = 0
    cohere_embed_calls: int = 0
    cohere_rerank_calls: int = 0
    top_rerank_score: float = 0.0

    # Retrieval evaluation flags
    hit_at_5: bool = False
    hit_at_10: bool = False
    reciprocal_rank: float = 0.0

    # Generation evaluation flags
    faithfulness_score: float = 1.0
    relevance_score: float = 1.0
    citation_valid: bool = True


class AggregateMetrics(BaseModel):
    """Aggregated benchmark metrics across an evaluation run."""

    total_queries: int
    direct_fact_count: int
    table_numbers_count: int
    multi_section_count: int
    not_in_corpus_count: int

    # Retrieval metrics
    recall_at_5: float
    recall_at_10: float
    mrr: float

    # Generation & Quality metrics
    faithfulness: float
    not_found_accuracy: float
    citation_accuracy: float

    # Performance & Cost metrics
    latency_p50_ms: float
    latency_p95_ms: float
    mean_latency_ms: float
    total_embed_calls: int
    total_rerank_calls: int
    total_tokens_used: int
    cost_estimate_usd: float = 0.0


class AblationConfig(BaseModel):
    """Ablation configuration specifying which RAG features are enabled."""

    name: str
    description: str
    use_dense: bool = True
    use_sparse: bool = True
    use_heading_fusion: bool = True
    use_cohere_rerank: bool = True
    use_window_expansion: bool = True
    not_found_threshold: float = 0.25


class AblationRow(BaseModel):
    """Performance metrics for an ablation configuration variant."""

    config_name: str
    description: str
    recall_at_5: float
    recall_at_10: float
    mrr: float
    faithfulness: float
    not_found_accuracy: float
    latency_p95_ms: float
    avg_tokens: float
