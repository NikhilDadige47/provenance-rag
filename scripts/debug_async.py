"""Standalone async test to debug the evaluator hang."""
import asyncio
import pathlib
import sys
import time
from unittest.mock import AsyncMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from eval.evaluate import Evaluator
from eval.models import EvalItem
from src.generation.prompt import PromptBuilder
from src.retrieval.expansion import ContextExpander
from src.retrieval.search import HybridSearchPipeline, RetrievedChunk, SearchResult
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager

# Build items
items = [
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

# Build env
tmp_path = pathlib.Path("./tmp_test")
tmp_path.mkdir(exist_ok=True)

db = DatabaseManager(db_path=tmp_path / "debug_test.db")
cfg = OwnerConfig(cohere_api_key="test_cohere_key", groq_api_key="test_groq_key", qdrant_url=":memory:")

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
    print(f"  mock_search called: {query[:40]}", flush=True)
    if "mars" in query.lower():
        return SearchResult(
            query=query,
            scope="demo",
            chunks=[RetrievedChunk(
                chunk_id="irr",
                doc_id="doc.pdf",
                parent_id="p_irr",
                title="Overview",
                breadcrumb="Overview",
                page=1,
                bbox=None,
                display_text="Irrelevant.",
                embedding_text="Irrelevant.",
                score=0.10,
            )],
            is_found=False,
        )
    return SearchResult(
        query=query,
        scope="demo",
        chunks=[RetrievedChunk(
            chunk_id="rel",
            doc_id="acme_annual_financial_report_2025.pdf",
            parent_id="p_rel",
            title="Summary",
            breadcrumb="Summary",
            page=1,
            bbox=None,
            display_text="Revenue $120 million FY2025.",
            embedding_text="Revenue $120 million FY2025.",
            score=0.92,
        )],
        is_found=True,
    )

searcher.search = AsyncMock(side_effect=mock_search)
expander = ContextExpander(db=db)
prompt_builder = PromptBuilder()

evaluator = Evaluator(
    searcher=searcher,
    reranker=mock_reranker,
    expander=expander,
    prompt_builder=prompt_builder,
    db=db,
    cfg=cfg,
)

print("=== Starting async evaluation ===", flush=True)

async def run():
    print("Inside run(), calling evaluate_item on item 0", flush=True)
    t0 = time.time()
    result = await evaluator.evaluate_item(items[0])
    print(f"Done item 0 in {time.time()-t0:.2f}s: {result.item_id} hit@5={result.hit_at_5}", flush=True)

    print("Calling evaluate_item on item 1 (not-found)", flush=True)
    result2 = await evaluator.evaluate_item(items[1])
    print(f"Done item 1 in {time.time()-t0:.2f}s: {result2.item_id} not_found={result2.not_found}", flush=True)

asyncio.run(run())
print("=== All done ===", flush=True)

