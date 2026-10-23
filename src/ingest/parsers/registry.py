"""Parser registry providing dynamic parser resolution and metadata.

Enables selecting a parser per document without hardcoded couplings.
"""

from __future__ import annotations

from typing import Any

from src.ingest.parsers.landingai import LandingAIAdapter
from src.ingest.parsers.llamaparse import LlamaParseAdapter
from src.ingest.parsers.local_pymupdf import LocalPyMuPDFParser
from src.interfaces import IParser


class ParserRegistry:
    """Registry managing available document parsers."""

    def __init__(self) -> None:
        self._parsers: dict[str, IParser] = {}
        # Register default supported parsers
        self.register(LocalPyMuPDFParser())
        self.register(LlamaParseAdapter())
        self.register(LandingAIAdapter())

    def register(self, parser: IParser) -> None:
        """Register a new parser adapter."""
        self._parsers[parser.name.lower()] = parser

    def get(self, name: str) -> IParser:
        """Retrieve parser by name."""
        name_clean = name.strip().lower()
        if name_clean not in self._parsers:
            raise KeyError(
                f"Unknown parser '{name}'. Available: {list(self._parsers.keys())}"
            )
        return self._parsers[name_clean]

    def is_valid_parser(self, name: str) -> bool:
        """Check if parser name is registered."""
        return name.strip().lower() in self._parsers

    def list_available(self) -> list[dict[str, Any]]:
        """List metadata for all available parsers."""
        return [
            {
                "name": p.name,
                "requires_key": p.requires_key,
                "is_local": not p.requires_key,
            }
            for p in self._parsers.values()
        ]


# Global singleton instance
default_parser_registry = ParserRegistry()
