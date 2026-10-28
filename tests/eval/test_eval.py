"""Unit and integration tests for Phase 7 Evaluation, Ablation, and Tier Verification."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from eval.ablation import AblationRunner
from eval.evaluate import Evaluator
from eval.gate import MetricFloors, assert_production_floors, assert_strategy_ordering
from eval.harness import OfflineEvalHarness
from eval.models import EvalItem
from eval.tier_checks import TierVerifier
from eval.tune_thresholds import ThresholdTuner
from src.generation.prompt import PromptBuilder
from src.retrieval.expansion import ContextExpander
from src.retrieval.search import HybridSearchPipeline, RetrievedChunk, SearchResult
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager


@pytest.fixture
def sample_golden_items() -> list[EvalItem]:
    """Sample golden set items covering all 4 categories."""
    return [
        EvalItem(
            id="f1",
            category="direct_fact",
            question="What was Acme's revenue?",
            expected_doc="acme_annual_financial_report_2025.pdf",
            expected_page=1,
            expected_answer="$120 million",
            keywords=["$120 million", "revenue"],
            is_not_found=False,
        ),
        EvalItem(
            id="n1",
            category="table_numbers",
            question="What is the debt-to-equity ratio?",
            expected_doc="acme_annual_financial_report_2025.pdf",
            expected_page=2,
            expected_answer="0.42",
            keywords=["0.42", "debt-to-equity"],
            is_not_found=False,
        ),
        EvalItem(
            id="s1",
            category="multi_section",
            question="Summarize capital health including assets and debt.",
            expected_doc="acme_annual_financial_report_2025.pdf",
            expected_page=2,
            expected_answer="$185 million assets with 0.42 debt ratio",
            keywords=["$185 million", "0.42"],
            is_not_found=False,
        ),
        EvalItem(
            id="nf1",
            category="not_in_corpus",
            question="What is the dividend policy on Mars?",
            expected_doc=None,
            expected_page=None,
            expected_answer="NOT_FOUND",
            keywords=[],
            is_not_found=True,
        ),
    ]


@pytest.fixture
def eval_env(tmp_path: Path):
    """Set up mocked evaluation components."""
    db = DatabaseManager(db_path=tmp_path / "test_eval.db")
    cfg = OwnerConfig(
        cohere_api_key="test_cohere_key",
        groq_api_key="test_groq_key",
        qdrant_url=":memory:",
    )
    mock_reranker = AsyncMock()
    async def mock_rerank(query, chunks, top_n=5, **kwargs):
        return chunks[:top_n]
    mock_reranker.rerank = AsyncMock(side_effect=mock_rerank)
    searcher = HybridSearchPipeline(
        embedder=AsyncMock(),
        store=AsyncMock(),
        reranker=mock_reranker,
    )

    async def mock_search(query: str, **kwargs) -> SearchResult:
        if "mars" in query.lower():
            # Return low scoring irrelevant candidates
            return SearchResult(
                query=query,
                scope="demo",
                chunks=[
                    RetrievedChunk(
                        chunk_id="chunk_irr",
                        doc_id="acme_annual_financial_report_2025.pdf",
                        parent_id="parent_irr",
                        title="Overview",
                        breadcrumb="Overview",
                        page=1,
                        bbox=None,
                        display_text="Irrelevant document content.",
                        embedding_text="Irrelevant document content.",
                        score=0.10,
                    )
                ],
                is_found=False,
            )

        # Return relevant matching candidates
        return SearchResult(
            query=query,
            scope="demo",
            chunks=[
                RetrievedChunk(
                    chunk_id="chunk_rel_1",
                    doc_id="acme_annual_financial_report_2025.pdf",
                    parent_id="parent_rel_1",
                    title="Executive Summary",
                    breadcrumb="Executive Summary",
                    page=1,
                    bbox=None,
                    display_text="Acme Corporation recorded consolidated revenue of $120 million in FY2025.",
                    embedding_text="Acme Corporation recorded consolidated revenue of $120 million in FY2025.",
                    score=0.92,
                ),
                RetrievedChunk(
                    chunk_id="chunk_rel_2",
                    doc_id="acme_annual_financial_report_2025.pdf",
                    parent_id="parent_rel_2",
                    title="Balance Sheet",
                    breadcrumb="Balance Sheet",
                    page=2,
                    bbox=None,
                    display_text="Total consolidated assets stood at $185 million with debt-to-equity ratio of 0.42.",
                    embedding_text="Total consolidated assets stood at $185 million with debt-to-equity ratio of 0.42.",
                    score=0.88,
                ),
            ],
            is_found=True,
        )

    searcher.search = AsyncMock(side_effect=mock_search)
    reranker = mock_reranker
    expander = ContextExpander(db=db)
    prompt_builder = PromptBuilder()

    evaluator = Evaluator(
        searcher=searcher,
        reranker=reranker,
        expander=expander,
        prompt_builder=prompt_builder,
        db=db,
        cfg=cfg,
    )

    return evaluator, db, cfg


def test_golden_set_file_validity() -> None:
    """Verify eval/golden_set.jsonl exists and contains valid benchmark questions."""
    items = Evaluator.load_golden_set(Path("eval/golden_set.jsonl"))
    assert len(items) == 50, f"Expected 50 items in golden set, found {len(items)}"

    categories = {i.category for i in items}
    assert "direct_fact" in categories
    assert "table_numbers" in categories
    assert "multi_section" in categories
    assert "not_in_corpus" in categories

    for item in items:
        assert item.question, f"Empty question in item {item.id}"
        if item.is_not_found:
            assert item.expected_answer == "NOT_FOUND"
        else:
            assert len(item.keywords) > 0, f"Item {item.id} must have keywords"


@pytest.mark.asyncio
async def test_evaluator_run_evaluation(eval_env, sample_golden_items: list[EvalItem]) -> None:
    """Test full evaluation pipeline computes recall, MRR, faithfulness, and latency."""
    evaluator, db, cfg = eval_env

    results, aggregate = await evaluator.run_evaluation(
        items=sample_golden_items,
        not_found_threshold=0.25,
        use_rerank=True,
        use_expansion=True,
    )

    assert len(results) == 4
    assert aggregate.total_queries == 4
    assert aggregate.recall_at_5 > 0.0
    assert aggregate.mrr > 0.0
    assert aggregate.faithfulness > 0.0
    assert aggregate.not_found_accuracy == 100.0  # Mars question correctly rejected
    assert aggregate.latency_p50_ms >= 0.0


@pytest.mark.asyncio
async def test_ablation_runner(
    eval_env, sample_golden_items: list[EvalItem], tmp_path: Path
) -> None:
    """Test ablation runner executes all configurations and saves markdown report."""
    evaluator, db, cfg = eval_env
    runner = AblationRunner(evaluator=evaluator)

    out_file = tmp_path / "test_ablation.md"
    rows = await runner.run_all(items=sample_golden_items, output_file=out_file)

    assert len(rows) == 4
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Ablation Comparison Table" in content
    assert "Senior Takeaways" in content


@pytest.mark.asyncio
async def test_retrieval_accuracy_regression_gate(tmp_path: Path) -> None:
    """CI quality gate: score the 50-question golden set on dual local indexes.

    Fails the build when the rerank pipeline drops below eval/results/floors.json
    or when reranking no longer beats simple chunking.
    """
    items = Evaluator.load_golden_set()
    assert len(items) == 50

    runner = AblationRunner(harness=OfflineEvalHarness.from_fixture())
    rows = await runner.run_all(items=items, output_file=tmp_path / "ablation.md")
    floors = MetricFloors.load()
    by_name = {row.config_name: row for row in rows}

    assert_production_floors(by_name["4_reranking"], floors)
    assert_strategy_ordering(rows, floors)


@pytest.mark.asyncio
async def test_threshold_tuning(eval_env, sample_golden_items: list[EvalItem]) -> None:
    """Test threshold calibration identifies clear separation between answerable and trick queries."""
    evaluator, db, cfg = eval_env
    tuner = ThresholdTuner(evaluator=evaluator)

    calib = await tuner.calibrate_not_found_threshold(items=sample_golden_items)
    assert calib.recommended_threshold >= 0.20
    assert calib.recommended_threshold <= 0.35
    assert calib.min_answerable_score > calib.max_not_found_score
    assert (
        "recommends" in calib.decision_rationale.lower()
        or "cutoff" in calib.decision_rationale.lower()
    )


def test_tier_verifier(tmp_path: Path) -> None:
    """Test TierVerifier validates all three tiers (A, B, C) and security constraints."""
    db = DatabaseManager(db_path=tmp_path / "test_tiers.db")
    cfg = OwnerConfig(
        cohere_api_key="test_cohere",
        groq_api_key="test_groq",
        qdrant_url=":memory:",
    )
    verifier = TierVerifier(db=db, cfg=cfg)

    checks = verifier.run_all_checks()
    assert len(checks) >= 5

    for c in checks:
        assert c.passed, f"Tier check failed: {c.tier_name} - {c.check_name}: {c.details}"
