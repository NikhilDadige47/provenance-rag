"""Tests for conditional query rewriter."""

from unittest.mock import MagicMock

import pytest

from src.generation.rewrite import rewrite_query_if_needed


@pytest.mark.asyncio
async def test_rewrite_first_turn_bypasses():
    """Verify first-turn questions bypass rewriting with zero LLM calls."""
    mock_llm = MagicMock()
    result = await rewrite_query_if_needed(
        query="What is the net revenue for 2025?",
        history=None,
        llm=mock_llm,
    )
    assert result == "What is the net revenue for 2025?"
    mock_llm.generate_stream.assert_not_called()


@pytest.mark.asyncio
async def test_rewrite_follow_up_with_history():
    """Verify follow-up turns call LLM and rewrite pronouns."""
    mock_llm = MagicMock()

    async def mock_generate_stream(prompt, api_key=None, model=None):
        yield "What were Acme's total operating expenses in 2025?"

    mock_llm.generate_stream = mock_generate_stream

    history = [
        {"role": "user", "content": "Tell me about Acme's 2025 performance."},
        {"role": "assistant", "content": "Acme reported strong revenue in 2025."},
    ]

    result = await rewrite_query_if_needed(
        query="How much were their operating expenses?",
        history=history,
        llm=mock_llm,
    )

    assert result == "What were Acme's total operating expenses in 2025?"
