"""Tests for the ParserRegistry."""

import pytest

from src.ingest.parsers.registry import ParserRegistry, default_parser_registry


def test_default_registry_parsers() -> None:
    available = default_parser_registry.list_available()
    names = [p["name"] for p in available]

    assert "local_pymupdf" in names
    assert "llamaparse" in names
    assert "landingai" in names

    assert default_parser_registry.is_valid_parser("local_pymupdf") is True
    assert default_parser_registry.is_valid_parser("llamaparse") is True
    assert default_parser_registry.is_valid_parser("unknown_xyz") is False


def test_registry_get_and_unknown() -> None:
    reg = ParserRegistry()
    p = reg.get("local_pymupdf")
    assert p.name == "local_pymupdf"

    with pytest.raises(KeyError):
        reg.get("unsupported_service")
