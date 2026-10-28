"""Generation layer: prompt construction, LLM adapters, citation verification, and query rewrite."""

from src.generation.citations import CitationAuditResult, VerifiedSource, audit_citations
from src.generation.llm import (
    AnthropicLLM,
    GeminiLLM,
    GroqLLM,
    MistralLLM,
    OpenAILLM,
    get_llm_adapter,
)
from src.generation.prompt import build_generation_prompt, validate_question
from src.generation.rewrite import rewrite_query_if_needed

__all__ = [
    "AnthropicLLM",
    "CitationAuditResult",
    "GeminiLLM",
    "GroqLLM",
    "MistralLLM",
    "OpenAILLM",
    "VerifiedSource",
    "audit_citations",
    "build_generation_prompt",
    "get_llm_adapter",
    "rewrite_query_if_needed",
    "validate_question",
]
