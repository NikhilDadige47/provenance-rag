"""Tests for key transport and ephemeral lifecycle."""

import pytest

from src.security.context import (
    EphemeralJobContext,
    get_request_llm_key,
    get_request_llm_model,
    get_request_llm_provider,
    request_llm_context,
)
from src.security.secret import Secret


def test_request_llm_context_lifecycle() -> None:
    # Initially none
    assert get_request_llm_key() is None
    assert get_request_llm_provider() is None

    key = Secret("sk-visitor-llm-key-12345")
    with request_llm_context(llm_key=key, provider="groq", model="llama-3.3-70b"):
        assert get_request_llm_key() == key
        assert get_request_llm_provider() == "groq"
        assert get_request_llm_model() == "llama-3.3-70b"

    # Must be reset after context exits
    assert get_request_llm_key() is None
    assert get_request_llm_provider() is None
    assert get_request_llm_model() is None


def test_ephemeral_job_context_lifecycle() -> None:
    parser_key = Secret("llx-parser-key-99999")
    ctx = EphemeralJobContext(parser_name="llamaparse", parser_key=parser_key)

    assert ctx.get_key() == parser_key

    # Explicit cleanup destroys key
    ctx.cleanup()
    with pytest.raises(RuntimeError):
        ctx.get_key()


def test_ephemeral_job_context_context_manager() -> None:
    parser_key = Secret("llx-parser-key-88888")
    with EphemeralJobContext(parser_name="llamaparse", parser_key=parser_key) as job:
        assert job.get_key() == parser_key

    # Destroyed upon exit
    with pytest.raises(RuntimeError):
        job.get_key()
