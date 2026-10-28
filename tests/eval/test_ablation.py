"""Dual-index ablation tests: simple vs semantic chunking actually differ."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.ablation import AblationRunner
from eval.evaluate import Evaluator
from eval.harness import OfflineEvalHarness
from eval.strategies import ABLATION_CONFIGS, config_by_name


def test_simple_and_semantic_indexes_are_distinct() -> None:
    harness = OfflineEvalHarness.from_fixture()
    simple_ids = {child.chunk_id for child in harness.bundle.simple.children}
    semantic_ids = {child.chunk_id for child in harness.bundle.semantic.children}
    assert simple_ids
    assert semantic_ids
    assert simple_ids != semantic_ids

    fused = [
        child.embedding_text
        for child in harness.bundle.semantic.children
        if child.embedding_text.startswith("[")
    ]
    unfused = [
        child
        for child in harness.bundle.simple.children
        if child.embedding_text == child.display_text
    ]
    assert fused, "semantic index must apply heading fusion"
    assert len(unfused) == len(harness.bundle.simple.children)


def test_ablation_configs_cover_four_named_strategies() -> None:
    names = [cfg.name for cfg in ABLATION_CONFIGS]
    assert names == [
        "1_simple_chunking",
        "2_semantic_chunking",
        "3_hybrid_search",
        "4_reranking",
    ]
    assert config_by_name("1_simple_chunking").chunker == "simple"
    assert config_by_name("2_semantic_chunking").chunker == "semantic"
    assert config_by_name("3_hybrid_search").use_sparse is True
    assert config_by_name("4_reranking").use_cohere_rerank is True


@pytest.mark.asyncio
async def test_offline_ablation_writes_differentiated_report(tmp_path: Path) -> None:
    items = Evaluator.load_golden_set()
    runner = AblationRunner(harness=OfflineEvalHarness.from_fixture())
    out = tmp_path / "ablation.md"
    rows = await runner.run_all(items=items, output_file=out)

    assert len(rows) == 4
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Simple Chunking" in content
    assert "Semantic Chunking" in content
    assert "Hybrid Search" in content
    assert "Reranking" in content

    metrics = {(row.config_name, row.recall_at_5, row.mrr) for row in rows}
    assert len(metrics) > 1, "ablation configs must not all produce identical metrics"

    by_name = {row.config_name: row for row in rows}
    assert by_name["2_semantic_chunking"].recall_at_5 > by_name["1_simple_chunking"].recall_at_5
    assert by_name["4_reranking"].mrr > by_name["3_hybrid_search"].mrr
    assert by_name["4_reranking"].not_found_accuracy > by_name["3_hybrid_search"].not_found_accuracy
