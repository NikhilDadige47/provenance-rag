"""Core abstract interfaces for Provenance RAG.

Every provider adapter and processing pipeline step implements these contracts,
keeping the core engine decoupled from vendor SDKs.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from src.security.secret import Secret


class IParser(ABC):
    """Abstract contract for document parsers (LlamaParse, LandingAI, Unstructured, PyMuPDF)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this parser (e.g., 'llamaparse', 'local_pymupdf')."""
        pass

    @property
    @abstractmethod
    def requires_key(self) -> bool:
        """True if this parser requires a visitor API key; False for local free parsers."""
        pass

    @abstractmethod
    async def parse(self, file_path: Path, api_key: Secret | None = None) -> Any:
        """Parse a document and return the raw parser-specific result."""
        pass


class IChunker(ABC):
    """Abstract contract for chunking engines (hybrid recursive + parent-child)."""

    @abstractmethod
    def chunk(self, structured_doc: Any, config: Any | None = None) -> Any:
        """Transform a StructuredDoc into parents and children chunks."""
        pass


class IEmbedder(ABC):
    """Abstract contract for vector embeddings (e.g., Cohere Embed)."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier (e.g., 'embed-english-v3.0')."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension (e.g., 1024)."""
        pass

    @abstractmethod
    async def embed(
        self, texts: list[str], input_type: str = "search_document"
    ) -> list[list[float]]:
        """Compute dense vector embeddings for input texts."""
        pass


class IReranker(ABC):
    """Abstract contract for two-stage rerankers (e.g., Cohere Rerank)."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Reranker model name."""
        pass

    @abstractmethod
    async def rerank(
        self, query: str, documents: list[str], top_n: int = 5
    ) -> list[dict[str, Any]]:
        """Rerank candidate documents against the query and return scored results."""
        pass


class ILLM(ABC):
    """Abstract contract for answer generation LLMs (Owner default or Visitor BYOK)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the LLM provider (e.g., 'groq', 'openai', 'anthropic')."""
        pass

    @abstractmethod
    async def generate_stream(
        self, prompt: str, api_key: Secret | None = None, model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream generated tokens for the prompt."""
        pass
