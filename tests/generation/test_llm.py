"""Tests for LLM adapters (Groq, OpenAI, Anthropic) and error handling."""

from unittest.mock import AsyncMock, patch

import pytest

from src.generation.llm import AnthropicLLM, GroqLLM, OpenAILLM, get_llm_adapter
from src.security.errors import InvalidKeyError
from src.security.secret import Secret


@pytest.mark.asyncio
async def test_groq_llm_streaming_success():
    """Verify Groq adapter streams token chunks from SSE stream."""
    llm = GroqLLM(api_key=Secret("gsk-test-valid-key"))

    sse_lines = [
        'data: {"choices": [{"delta": {"content": "Hello"}}]}',
        'data: {"choices": [{"delta": {"content": " world"}}]}',
        'data: [DONE]',
    ]

    mock_resp = AsyncMock()
    mock_resp.status_code = 200

    async def aiter_lines_gen():
        for line in sse_lines:
            yield line

    mock_resp.aiter_lines = aiter_lines_gen
    mock_resp.__aenter__.return_value = mock_resp

    with patch.object(llm._http_client, "stream", return_value=mock_resp):
        tokens = []
        async for token in llm.generate_stream("Hi"):
            tokens.append(token)

        assert "".join(tokens) == "Hello world"


@pytest.mark.asyncio
async def test_openai_llm_missing_key_raises():
    """Verify OpenAI BYOK adapter fails fast when key is missing."""
    llm = OpenAILLM(api_key=Secret(""))
    with pytest.raises(InvalidKeyError):
        async for _ in llm.generate_stream("Hi"):
            pass


@pytest.mark.asyncio
async def test_anthropic_llm_streaming_success():
    """Verify Anthropic Messages API adapter parses content_block_delta."""
    llm = AnthropicLLM(api_key=Secret("sk-ant-test-key"))

    sse_lines = [
        'data: {"type": "content_block_delta", "delta": {"text": "Cited "}}',
        'data: {"type": "content_block_delta", "delta": {"text": "answer."}}',
    ]

    mock_resp = AsyncMock()
    mock_resp.status_code = 200

    async def aiter_lines_gen():
        for line in sse_lines:
            yield line

    mock_resp.aiter_lines = aiter_lines_gen
    mock_resp.__aenter__.return_value = mock_resp

    with patch.object(llm._http_client, "stream", return_value=mock_resp):
        tokens = []
        async for token in llm.generate_stream("Test"):
            tokens.append(token)

        assert "".join(tokens) == "Cited answer."


def test_get_llm_adapter_factory():
    """Verify factory returns appropriate adapter for owner default vs visitor key."""
    # Owner default (no visitor key) -> Groq
    default_adapter = get_llm_adapter(api_key=None)
    assert isinstance(default_adapter, GroqLLM)

    # Visitor key with OpenAI
    openai_adapter = get_llm_adapter(provider="openai", api_key=Secret("sk-proj-test"))
    assert isinstance(openai_adapter, OpenAILLM)

    # Visitor key with Anthropic
    anthropic_adapter = get_llm_adapter(provider="anthropic", api_key=Secret("sk-ant-test"))
    assert isinstance(anthropic_adapter, AnthropicLLM)
