"""Run the 50-query golden-set evaluation and retrieval ablation.

Default (offline): fixture corpus + local hashing embeddings. No API keys.
Used by CI.

--live: Qdrant scope=demo (parsed with local PyMuPDF, Cohere-embedded).
Strategies 2-4 share that index; strategy 4 uses Cohere Rerank.
Strategy 1 is skipped (simple chunks are not stored in the demo index).

Writes:
- eval/results/metrics.json
- eval/results/summary.md
- eval/results/ablation.md
- eval/results/thresholds_and_caps.md
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from eval.ablation import AblationRunner
from eval.evaluate import Evaluator
from eval.harness import OfflineEvalHarness
from eval.live import LiveEvalHarness, LiveIndexError
from eval.strategies import LIVE_ABLATION_CONFIGS, config_by_name
from eval.tier_checks import TierVerifier
from eval.tune_thresholds import ThresholdTuner
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_runner")


async def _run(live: bool) -> None:
    items = Evaluator.load_golden_set()
    logger.info("Loaded %s curated benchmark questions.", len(items))

    if live:
        logger.info("Live eval: Qdrant scope=demo, parser=local_pymupdf, Cohere Embed/Rerank.")
        try:
            harness: OfflineEvalHarness | LiveEvalHarness = LiveEvalHarness()
        except LiveIndexError as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
        rerank_config = config_by_name("4_reranking")
        configs = LIVE_ABLATION_CONFIGS
        index_note = (
            "Live evaluation against Qdrant scope=demo. Documents were parsed with "
            "local PyMuPDF and Cohere-embedded once. Strategies 2-4 share that index; "
            "strategy 4 applies Cohere Rerank. Strategy 1 (simple chunking) is omitted "
            "because those windows are not stored in the demo collection."
        )
    else:
        logger.info("Offline eval: fixture corpus + local hashing embeddings.")
        harness = OfflineEvalHarness.from_fixture()
        rerank_config = config_by_name("4_reranking")
        configs = None
        index_note = None

    evaluator = harness.evaluator(rerank_config)

    logger.info("Executing production (rerank) evaluation...")
    results, aggregate = await evaluator.run_evaluation(
        items=items,
        not_found_threshold=rerank_config.not_found_threshold,
        use_rerank=True,
        use_expansion=True,
    )
    json_path, md_path = Evaluator.save_reports(aggregate, results, Path("eval/results"))
    logger.info("Evaluation report saved to %s and %s", md_path, json_path)

    logger.info("Executing retrieval ablation...")
    runner = AblationRunner(harness=harness)
    ablation_file = Path("eval/results/ablation.md")
    await runner.run_all(
        items=items,
        output_file=ablation_file,
        configs=configs,
        index_note=index_note,
    )
    logger.info("Ablation study saved to %s", ablation_file)

    logger.info("Calibrating not-found threshold and cost caps...")
    tuner = ThresholdTuner(evaluator=evaluator)
    calib = await tuner.calibrate_not_found_threshold(items=items)
    cost_rec = ThresholdTuner.calculate_cost_budget_recommendations(results)
    tuning_file = Path("eval/results/thresholds_and_caps.md")
    ThresholdTuner.save_tuning_report(calib, cost_rec, output_file=tuning_file)
    logger.info("Threshold report saved to %s", tuning_file)

    logger.info("Verifying tier boundaries...")
    db = DatabaseManager(Path("provenance_rag.db"))
    verifier = TierVerifier(db=db, cfg=OwnerConfig.from_env())
    checks = verifier.run_all_checks()
    all_passed = all(check.passed for check in checks)
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        logger.info("[%s] %s - %s: %s", status, check.tier_name, check.check_name, check.details)

    if all_passed:
        logger.info("All tier checks passed.")
    else:
        logger.error("One or more tier checks failed.")
        raise SystemExit(1)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run golden-set evaluation.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Score against Qdrant scope=demo with Cohere (requires ingest_demo + API key).",
    )
    args = parser.parse_args()
    await _run(live=args.live)


if __name__ == "__main__":
    asyncio.run(main())
