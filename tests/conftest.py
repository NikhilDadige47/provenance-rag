"""Pytest fixtures for Provenance RAG test suite."""

import pytest

from src.security.secret import Secret


@pytest.fixture(autouse=True)
def _clear_turso_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests use local SQLite files, not a developer's Turso account.

    Empty strings win over .env because load_dotenv does not override set vars.
    """
    monkeypatch.setenv("TURSO_DATABASE_URL", "")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")


@pytest.fixture
def fake_openai_key() -> Secret:
    return Secret("sk-test-fake-openai-secret-key-1234567890")


@pytest.fixture
def fake_cohere_key() -> Secret:
    return Secret("co-test-fake-cohere-secret-key-1234567890")


@pytest.fixture
def fake_llamaparse_key() -> Secret:
    return Secret("llx-test-fake-llamaparse-key-1234567890")
