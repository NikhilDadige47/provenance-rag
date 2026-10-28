"""Provider catalog for supported Document Parsers and BYOK LLMs.

Adheres to Roadmap P1-T2:
Contains documentation links, key requirements, recommended models, and notes.
"""

from typing import Any

from pydantic import BaseModel, Field


class ProviderEntry(BaseModel):
    name: str
    category: str = Field(description="'parser' or 'llm'")
    display_name: str
    requires_key: bool
    key_prefix: str | None = None
    docs_url: str
    notes: str
    recommended_models: list[str] = Field(default_factory=list)


PROVIDER_CATALOG: dict[str, ProviderEntry] = {
    # --- Document Parsers ---
    "local_pymupdf": ProviderEntry(
        name="local_pymupdf",
        category="parser",
        display_name="Free Local Parser (PyMuPDF)",
        requires_key=False,
        docs_url="https://pymupdf.readthedocs.io",
        notes="Zero keys required. Uses font-size heuristics to extract headings and clean text.",
    ),
    "llamaparse": ProviderEntry(
        name="llamaparse",
        category="parser",
        display_name="LlamaParse (LlamaIndex Cloud)",
        requires_key=True,
        key_prefix="llx-",
        docs_url="https://docs.cloud.llamaindex.ai",
        notes="High quality extraction for complex PDFs and markdown tables. Requires visitor API key.",
    ),
    "landingai": ProviderEntry(
        name="landingai",
        category="parser",
        display_name="Landing AI ADE",
        requires_key=True,
        docs_url="https://landing.ai/ade",
        notes="Agentic Document Extraction with spatial bounding box grounding. Requires visitor key.",
    ),
    # --- LLM Providers (BYOK) ---
    "groq": ProviderEntry(
        name="groq",
        category="llm",
        display_name="GroqCloud (Llama 3.3)",
        requires_key=True,
        key_prefix="gsk_",
        docs_url="https://console.groq.com/docs",
        notes="Ultra-low latency inference. Default owner LLM provider.",
        recommended_models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    ),
    "openai": ProviderEntry(
        name="openai",
        category="llm",
        display_name="OpenAI",
        requires_key=True,
        key_prefix="sk-",
        docs_url="https://platform.openai.com/docs",
        notes="Support for GPT-4o and GPT-4o-mini with visitor BYOK key.",
        recommended_models=["gpt-4o", "gpt-4o-mini"],
    ),
    "anthropic": ProviderEntry(
        name="anthropic",
        category="llm",
        display_name="Anthropic Claude",
        requires_key=True,
        key_prefix="sk-ant-",
        docs_url="https://docs.anthropic.com",
        notes="Support for Claude 3.5 Sonnet with visitor BYOK key.",
        recommended_models=["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
    ),
    "gemini": ProviderEntry(
        name="gemini",
        category="llm",
        display_name="Google Gemini",
        requires_key=True,
        docs_url="https://ai.google.dev/gemini-api/docs",
        notes="Visitor BYOK for Gemini Flash/Pro. Key is request-scoped only.",
        recommended_models=["gemini-1.5-flash-latest", "gemini-1.5-pro-latest"],
    ),
    "mistral": ProviderEntry(
        name="mistral",
        category="llm",
        display_name="Mistral AI",
        requires_key=True,
        docs_url="https://docs.mistral.ai",
        notes="Visitor BYOK for Mistral chat models. Key is request-scoped only.",
        recommended_models=["mistral-small-latest", "mistral-large-latest"],
    ),
}


def get_provider_info(name: str) -> ProviderEntry | None:
    """Retrieve catalog entry by provider name."""
    return PROVIDER_CATALOG.get(name.strip().lower())


def list_providers(category: str | None = None) -> list[dict[str, Any]]:
    """List all available providers, optionally filtered by category."""
    entries = PROVIDER_CATALOG.values()
    if category:
        entries = [e for e in entries if e.category == category]
    return [e.model_dump() for e in entries]
