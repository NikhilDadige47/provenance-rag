"""Pytest fixtures for Provenance RAG test suite."""

import pytest

from src.security.secret import Secret


@pytest.fixture
def fake_openai_key() -> Secret:
    return Secret("sk-test-fake-openai-secret-key-1234567890")


@pytest.fixture
def fake_cohere_key() -> Secret:
    return Secret("co-test-fake-cohere-secret-key-1234567890")


@pytest.fixture
def fake_llamaparse_key() -> Secret:
    return Secret("llx-test-fake-llamaparse-key-1234567890")
