"""Conditional query rewriter for multi-turn conversational follow-ups.

Implements roadmap P4-T7 & architecture §5:
- Evaluates conversation history
- Only triggers when previous turns exist; zero LLM calls on first-turn questions
- De-references ambiguous pronouns ('it', 'they', 'the former') into standalone queries
- Robust fallback to original query on any exception
"""

import logging

from src.interfaces import ILLM
from src.security.secret import Secret

logger = logging.getLogger(__name__)

REWRITE_PROMPT_TEMPLATE = """You are an expert query de-referencing assistant for a document retrieval engine.
Given the chat history and the latest user follow-up question, rewrite the follow-up question so that it is completely self-contained and standalone.
Preserve the exact user intent. DO NOT answer the question. Only return the rephrased question.

CHAT HISTORY:
{history_formatted}

FOLLOW-UP QUESTION:
{query}

STANDALONE QUESTION:"""


async def rewrite_query_if_needed(
    query: str,
    history: list[dict[str, str]] | None,
    llm: ILLM,
    api_key: Secret | None = None,
) -> str:
    """Rewrite a follow-up query to be standalone if chat history is present.

    Args:
        query: Latest user question.
        history: Prior conversation turns [{'role': 'user'|'assistant', 'content': '...'}].
        llm: Active LLM adapter to execute the rewrite.
        api_key: Optional visitor key.

    Returns:
        Standalone search query string.
    """
    clean_q = query.strip()
    if not history:
        # First turn: zero rewrite cost, return verbatim
        return clean_q

    # Format history turns (last 3 turns max for budget)
    recent_history = history[-3:]
    lines: list[str] = []
    for turn in recent_history:
        role = turn.get("role", "user").capitalize()
        content = turn.get("content", "").strip()
        lines.append(f"{role}: {content}")
    history_formatted = "\n".join(lines)

    prompt = REWRITE_PROMPT_TEMPLATE.format(
        history_formatted=history_formatted,
        query=clean_q,
    )

    try:
        tokens: list[str] = []
        async for token in llm.generate_stream(prompt, api_key=api_key):
            tokens.append(token)

        rewritten = "".join(tokens).strip().strip('"').strip("'")
        if rewritten and len(rewritten) >= 3:
            logger.info(f"Query rewritten: '{clean_q}' -> '{rewritten}'")
            return rewritten

    except Exception as exc:
        logger.warning(f"Query rewriting failed ({exc}). Falling back to original query.")

    return clean_q
