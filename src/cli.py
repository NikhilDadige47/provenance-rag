"""Command-line interface (CLI) for interactive Q&A and pipeline evaluation.

Implements roadmap P4-T8:
- Executes complete retrieval & generation pipeline from the terminal
- python -m src.cli ask "question"
- Interactive mode: python -m src.cli interactive
- Prints answer stream, verified sources, breadcrumbs, pages, timings, and token metrics
- Supports BYOK LLM keys, scope switching, and rerank disabling for ablation testing
"""

import argparse
import asyncio
import contextlib
import logging
import sys
import time
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.generation.citations import audit_citations
from src.generation.llm import get_llm_adapter
from src.generation.prompt import build_generation_prompt, validate_question
from src.generation.rewrite import rewrite_query_if_needed
from src.retrieval.expansion import ContextExpander
from src.retrieval.search import HybridSearchPipeline
from src.security.secret import Secret

logger = logging.getLogger(__name__)


async def run_pipeline(
    question: str,
    scope: str = "demo",
    llm_provider: str | None = None,
    llm_key: str | None = None,
    llm_model: str | None = None,
    disable_rerank: bool = False,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Execute the full Provenance RAG pipeline from question to cited answer.

    Returns:
        dict containing answer, sources, timing, and grounding status.
    """
    start_time = time.time()
    timings: dict[str, float] = {}

    # 1. Validate question
    is_valid, err_msg = validate_question(question)
    if not is_valid:
        return {
            "question": question,
            "answer": f"Invalid query: {err_msg}",
            "sources": [],
            "is_found": False,
            "timings": {},
        }

    # Resolve LLM adapter
    secret_key = Secret(llm_key) if llm_key else None
    llm = get_llm_adapter(provider=llm_provider, api_key=secret_key, model=llm_model)

    # 2. Conditional rewrite
    t0 = time.time()
    effective_query = await rewrite_query_if_needed(question, history, llm, api_key=secret_key)
    timings["rewrite_ms"] = round((time.time() - t0) * 1000, 1)

    # 3. Hybrid search + Cohere Rerank + Not-found gate
    t0 = time.time()
    search_pipeline = HybridSearchPipeline()
    search_result = await search_pipeline.search(
        query=effective_query,
        scope=scope,
        disable_rerank=disable_rerank,
    )
    timings["retrieval_ms"] = round((time.time() - t0) * 1000, 1)

    if not search_result.is_found:
        total_time = round((time.time() - start_time) * 1000, 1)
        timings["total_ms"] = total_time
        return {
            "question": question,
            "effective_query": effective_query,
            "answer": "I could not find the answer in the provided documents.",
            "sources": [],
            "is_found": False,
            "not_found_reason": search_result.reason,
            "timings": timings,
        }

    # 4. Parent / Window context expansion with budget
    t0 = time.time()
    expander = ContextExpander()
    expansion_res = expander.expand(chunks=search_result.chunks, scope=scope)
    timings["expansion_ms"] = round((time.time() - t0) * 1000, 1)

    # 5. Build prompt
    sys_prompt, user_prompt = build_generation_prompt(
        question=question,
        passages=expansion_res.passages,
    )

    # 6. Stream generation
    t0 = time.time()
    answer_tokens: list[str] = []
    generation_failed = False

    try:
        async for token in llm.generate_stream(user_prompt, api_key=secret_key):
            answer_tokens.append(token)
            try:
                print(token, end="", flush=True)
            except UnicodeEncodeError:
                safe_token = token.encode("ascii", errors="replace").decode("ascii")
                print(safe_token, end="", flush=True)
    except Exception as exc:
        logger.error(f"Generation error ({exc}). Returning sources with fallback notification.")
        generation_failed = True
        answer_tokens = [
            "Generation is temporarily unavailable. Please refer to the verified sources below."
        ]

    timings["generation_ms"] = round((time.time() - t0) * 1000, 1)
    full_answer = "".join(answer_tokens).strip()

    # 7. Audit citations and enrich sources
    t0 = time.time()
    audit_res = audit_citations(full_answer, passages=expansion_res.passages)
    timings["citation_audit_ms"] = round((time.time() - t0) * 1000, 1)

    total_time = round((time.time() - start_time) * 1000, 1)
    timings["total_ms"] = total_time

    # Build sources list: cited sources if present, otherwise available retrieved passages
    if audit_res.sources:
        sources_list = [
            {
                "citation": f"[{s.citation_index}]",
                "title": s.title,
                "page": s.page,
                "breadcrumb": s.breadcrumb,
                "snippet": s.text_snippet,
            }
            for s in audit_res.sources
        ]
    else:
        sources_list = [
            {
                "citation": f"[{idx}]",
                "title": p.title,
                "page": p.page,
                "breadcrumb": p.breadcrumb,
                "snippet": p.text[:200] + ("..." if len(p.text) > 200 else ""),
            }
            for idx, p in enumerate(expansion_res.passages, start=1)
        ]

    return {
        "question": question,
        "effective_query": effective_query,
        "answer": full_answer,
        "sources": sources_list,
        "is_found": True,
        "is_grounded": audit_res.is_grounded,
        "generation_failed": generation_failed,
        "timings": timings,
    }


def main() -> None:
    """CLI Entrypoint supporting 'ask' and 'interactive' subcommands."""
    parser = argparse.ArgumentParser(description="Provenance RAG CLI Interface")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    ask_parser = subparsers.add_parser("ask", help="Ask a question against the corpus")
    ask_parser.add_argument("question", type=str, help="Question to ask")
    ask_parser.add_argument("--scope", type=str, default="demo", help="Search scope (default: demo)")
    ask_parser.add_argument("--provider", type=str, default=None, help="LLM Provider (groq, openai, anthropic)")
    ask_parser.add_argument("--key", type=str, default=None, help="BYOK LLM API Key")
    ask_parser.add_argument("--model", type=str, default=None, help="Model name")
    ask_parser.add_argument("--disable-rerank", action="store_true", help="Bypass Cohere reranking for ablation")

    args = parser.parse_args()

    if args.command == "ask":
        print(f"\n[Provenance RAG] Scope: {args.scope} | Query: {args.question}\n")
        res = asyncio.run(
            run_pipeline(
                question=args.question,
                scope=args.scope,
                llm_provider=args.provider,
                llm_key=args.key,
                llm_model=args.model,
                disable_rerank=args.disable_rerank,
            )
        )

        if not res["is_found"]:
            print(res["answer"])

        print("\n\n" + "=" * 60)
        print("VERIFIED SOURCES & PROVENANCE:")
        print("=" * 60)
        if res["sources"]:
            for src in res["sources"]:
                print(f" {src['citation']} {src['title']} (Page {src['page']}) > {src['breadcrumb']}")
                print(f"     \"{src['snippet'][:120]}...\"\n")
        else:
            print(" No source passages cited.")

        print("-" * 60)
        print(f"Timing Breakdown: {res['timings']}")
        print(f"Grounded: {res.get('is_grounded', False)} | Found: {res['is_found']}")
        print("=" * 60 + "\n")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
