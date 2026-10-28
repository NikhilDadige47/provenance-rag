"""Four-way retrieval ablation over simple vs semantic indexes.

Strategies:
1. Simple Chunking — fixed-size windows, dense search, no rerank
2. Semantic Chunking — heading-aware windows, dense search, no rerank
3. Hybrid Search — semantic chunks + dense + BM25, no rerank
4. Reranking — hybrid + rerank + parent expansion
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from eval.evaluate import Evaluator
from eval.harness import OfflineEvalHarness
from eval.models import AblationConfig, AblationRow, EvalItem
from eval.strategies import ABLATION_CONFIGS

logger = logging.getLogger("provenance_rag.eval.ablation")


class SupportsEval(Protocol):
    def evaluator(self, config: AblationConfig) -> Evaluator: ...


class AblationRunner:
    """Executes ablation suites against either a live searcher or dual local indexes."""

    def __init__(
        self,
        evaluator: Evaluator | None = None,
        harness: SupportsEval | OfflineEvalHarness | None = None,
    ) -> None:
        if evaluator is None and harness is None:
            harness = OfflineEvalHarness.from_fixture()
        self.evaluator = evaluator
        self.harness = harness

    def _evaluator_for(self, config: AblationConfig) -> Evaluator:
        if self.harness is not None:
            return self.harness.evaluator(config)
        if self.evaluator is None:
            raise RuntimeError("AblationRunner requires an Evaluator or OfflineEvalHarness")
        return self.evaluator

    async def run_ablation_experiment(
        self,
        config: AblationConfig,
        items: list[EvalItem],
    ) -> AblationRow:
        """Run a single ablation configuration across the benchmark dataset."""
        logger.info("Running ablation configuration: %s (%s)", config.name, config.description)
        evaluator = self._evaluator_for(config)
        searcher = evaluator.searcher
        orig_dense = searcher.dense_weight
        orig_sparse = searcher.sparse_weight
        searcher.dense_weight = 1.0 if config.use_dense else 0.0
        searcher.sparse_weight = 1.0 if config.use_sparse else 0.0

        try:
            results, agg = await evaluator.run_evaluation(
                items=items,
                not_found_threshold=config.not_found_threshold,
                use_rerank=config.use_cohere_rerank,
                use_expansion=config.use_window_expansion,
            )
            avg_tokens = sum(r.tokens_used for r in results) / len(results) if results else 0.0
            return AblationRow(
                config_name=config.name,
                description=config.description,
                recall_at_5=agg.recall_at_5,
                recall_at_10=agg.recall_at_10,
                mrr=agg.mrr,
                faithfulness=agg.faithfulness,
                not_found_accuracy=agg.not_found_accuracy,
                latency_p95_ms=agg.latency_p95_ms,
                avg_tokens=round(avg_tokens, 1),
            )
        finally:
            searcher.dense_weight = orig_dense
            searcher.sparse_weight = orig_sparse

    async def run_all(
        self,
        items: list[EvalItem] | None = None,
        output_file: Path = Path("eval/results/ablation.md"),
        configs: list[AblationConfig] | None = None,
        index_note: str | None = None,
    ) -> list[AblationRow]:
        """Run ablation variants and save a markdown comparison table."""
        selected = configs or ABLATION_CONFIGS
        if items is None:
            loader = self.evaluator or self._evaluator_for(selected[-1])
            items = loader.load_golden_set()

        rows: list[AblationRow] = []
        for cfg in selected:
            rows.append(await self.run_ablation_experiment(cfg, items=items))

        self.save_ablation_table(rows, output_file=output_file, index_note=index_note)
        return rows

    @classmethod
    def save_ablation_table(
        cls,
        rows: list[AblationRow],
        output_file: Path = Path("eval/results/ablation.md"),
        index_note: str | None = None,
    ) -> None:
        """Write comparative ablation table with takeaways derived from measured rows."""
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        takeaways = cls._takeaways(rows)
        intro = index_note or (
            "Empirical comparison of retrieval techniques on the 50-query golden set. "
            "Simple and semantic configs use separate chunk indexes; hybrid and rerank "
            "reuse the semantic index."
        )

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Provenance RAG: Retrieval Strategy Ablation\n\n")
            f.write(f"{intro}\n\n")
            f.write("## Ablation Comparison Table\n\n")
            f.write(
                "| # | Configuration | Recall@5 | Recall@10 | MRR | Faithfulness | "
                "Not-Found Acc | Latency (p95) |\n"
            )
            f.write("|---|---|---|---|---|---|---|---|\n")
            for idx, row in enumerate(rows):
                f.write(
                    f"| {idx + 1} | **{row.description}** | `{row.recall_at_5}%` | "
                    f"`{row.recall_at_10}%` | `{row.mrr}` | `{row.faithfulness}%` | "
                    f"`{row.not_found_accuracy}%` | `{row.latency_p95_ms}ms` |\n"
                )
            f.write("\n## Senior Takeaways\n\n")
            f.write(takeaways)

    @staticmethod
    def _takeaways(rows: list[AblationRow]) -> str:
        if not rows:
            return "No ablation rows were produced.\n"
        best = max(rows, key=lambda row: (row.mrr, row.recall_at_5))
        worst = min(rows, key=lambda row: (row.mrr, row.recall_at_5))
        by_name = {row.config_name: row for row in rows}
        lines = [
            f"1. **Best measured configuration:** `{best.config_name}` "
            f"(MRR `{best.mrr}`, Recall@5 `{best.recall_at_5}%`).\n",
            f"2. **Weakest measured configuration:** `{worst.config_name}` "
            f"(MRR `{worst.mrr}`, Recall@5 `{worst.recall_at_5}%`).\n",
        ]
        simple = by_name.get("1_simple_chunking")
        semantic = by_name.get("2_semantic_chunking")
        if simple and semantic:
            delta = round(semantic.recall_at_5 - simple.recall_at_5, 2)
            lines.append(
                f"3. **Semantic vs simple chunking:** Recall@5 delta is `{delta}` points "
                "because heading-aware windows keep fiscal-year labels with the figures.\n"
            )
        hybrid = by_name.get("3_hybrid_search")
        rerank = by_name.get("4_reranking")
        if hybrid and rerank:
            lines.append(
                f"4. **Rerank vs hybrid:** MRR moves from `{hybrid.mrr}` to `{rerank.mrr}`; "
                "not-found accuracy moves from "
                f"`{hybrid.not_found_accuracy}%` to `{rerank.not_found_accuracy}%` "
                "because the second-stage scorer down-ranks out-of-corpus terms.\n"
            )
        return "\n".join(lines)
