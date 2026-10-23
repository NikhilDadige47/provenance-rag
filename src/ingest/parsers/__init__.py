"""Document parsers, normalizers, and quality gate package."""

from src.ingest.parsers.cleanup import (
    clean_blocks,
    fix_hyphenation,
    normalize_whitespace_and_unicode,
)
from src.ingest.parsers.landingai import LandingAIAdapter, LandingAINormalizer
from src.ingest.parsers.llamaparse import LlamaParseAdapter, LlamaParseNormalizer
from src.ingest.parsers.local_pymupdf import (
    LocalPyMuPDFParser,
    count_pages,
    extract_raw_reference_text,
)
from src.ingest.parsers.quality_gate import QualityGateResult, evaluate_parse_quality
from src.ingest.parsers.registry import ParserRegistry, default_parser_registry
from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc

__all__ = [
    "Block",
    "BlockType",
    "LandingAIAdapter",
    "LandingAINormalizer",
    "LlamaParseAdapter",
    "LlamaParseNormalizer",
    "LocalPyMuPDFParser",
    "ParserRegistry",
    "QualityGateResult",
    "StructuredDoc",
    "clean_blocks",
    "count_pages",
    "default_parser_registry",
    "evaluate_parse_quality",
    "extract_raw_reference_text",
    "fix_hyphenation",
    "normalize_whitespace_and_unicode",
]
