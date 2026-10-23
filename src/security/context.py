"""Key transport and ephemeral lifecycle management.

Enforces that:
1. LLM keys are request-scoped (via contextvars) and destroyed when the request completes.
2. Parser keys live in-memory only for the duration of an ingestion job and are explicitly cleared.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from src.security.secret import Secret

# Context variables for request-scoped visitor credentials
_current_llm_key: ContextVar[Secret | None] = ContextVar("current_llm_key", default=None)
_current_llm_provider: ContextVar[str | None] = ContextVar("current_llm_provider", default=None)
_current_llm_model: ContextVar[str | None] = ContextVar("current_llm_model", default=None)


def get_request_llm_key() -> Secret | None:
    """Retrieve the visitor's LLM key for the active request, if any."""
    return _current_llm_key.get()


def get_request_llm_provider() -> str | None:
    """Retrieve the visitor's chosen LLM provider for the active request."""
    return _current_llm_provider.get()


def get_request_llm_model() -> str | None:
    """Retrieve the visitor's requested LLM model for the active request."""
    return _current_llm_model.get()


@contextmanager
def request_llm_context(
    llm_key: Secret | None,
    provider: str | None = None,
    model: str | None = None,
) -> Generator[None, None, None]:
    """Context manager binding visitor LLM keys to the current async execution context.

    Automatically clears the keys when the context exits.
    """
    token_key = _current_llm_key.set(llm_key)
    token_prov = _current_llm_provider.set(provider)
    token_mod = _current_llm_model.set(model)
    try:
        yield
    finally:
        _current_llm_key.reset(token_key)
        _current_llm_provider.reset(token_prov)
        _current_llm_model.reset(token_mod)


class EphemeralJobContext:
    """Memory-only container for a parser key during an ingestion job.

    Guarantees that credentials cannot linger in memory after job completion or failure.
    """

    def __init__(self, parser_name: str, parser_key: Secret | None = None) -> None:
        self.parser_name = parser_name
        self._parser_key = parser_key
        self._active = True

    def get_key(self) -> Secret | None:
        """Access the key while the job context is active."""
        if not self._active:
            raise RuntimeError("Cannot access parser key: job context has already been cleaned up.")
        return self._parser_key

    def cleanup(self) -> None:
        """Immediately destroy the parser key from memory."""
        self._parser_key = None
        self._active = False

    def __enter__(self) -> "EphemeralJobContext":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.cleanup()
