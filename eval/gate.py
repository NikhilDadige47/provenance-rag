"""CI regression floors for retrieval accuracy."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from eval.models import AblationRow

DEFAULT_FLOORS_PATH = Path("eval/results/floors.json")


class MetricFloors(BaseModel):
    """Minimum acceptable metrics for the production (rerank) configuration."""

    min_recall_at_5: float = Field(ge=0.0, le=100.0)
    min_recall_at_10: float = Field(ge=0.0, le=100.0)
    min_mrr: float = Field(ge=0.0, le=1.0)
    min_not_found_accuracy: float = Field(ge=0.0, le=100.0)
    require_rerank_beats_simple: bool = True

    @classmethod
    def load(cls, path: Path = DEFAULT_FLOORS_PATH) -> MetricFloors:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


def assert_production_floors(row: AblationRow, floors: MetricFloors) -> None:
    """Fail the build when the rerank pipeline drops below recorded floors."""
    assert row.recall_at_5 >= floors.min_recall_at_5, (
        f"CI Build Failed: Recall@5 dropped to {row.recall_at_5}% "
        f"(minimum required: {floors.min_recall_at_5}%)"
    )
    assert row.recall_at_10 >= floors.min_recall_at_10, (
        f"CI Build Failed: Recall@10 dropped to {row.recall_at_10}% "
        f"(minimum required: {floors.min_recall_at_10}%)"
    )
    assert row.mrr >= floors.min_mrr, (
        f"CI Build Failed: MRR dropped to {row.mrr} (minimum required: {floors.min_mrr})"
    )
    assert row.not_found_accuracy >= floors.min_not_found_accuracy, (
        f"CI Build Failed: Not-Found Accuracy dropped to {row.not_found_accuracy}% "
        f"(minimum required: {floors.min_not_found_accuracy}%)"
    )


def assert_strategy_ordering(rows: list[AblationRow], floors: MetricFloors) -> None:
    """Require rerank to beat simple chunking when the floor file asks for it."""
    if not floors.require_rerank_beats_simple:
        return
    by_name = {row.config_name: row for row in rows}
    simple = by_name["1_simple_chunking"]
    rerank = by_name["4_reranking"]
    assert rerank.recall_at_5 >= simple.recall_at_5, (
        "CI Build Failed: reranking Recall@5 "
        f"({rerank.recall_at_5}%) did not beat simple chunking ({simple.recall_at_5}%)"
    )
    assert rerank.mrr >= simple.mrr, (
        f"CI Build Failed: reranking MRR ({rerank.mrr}) did not beat simple chunking ({simple.mrr})"
    )
