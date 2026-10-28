"""Shared tokenization helpers for offline retrieval evaluation."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z]+|\d+(?:\.\d+)?")
_COMMA_RE = re.compile(r"(?<=\d),(?=\d)")
_FY_RE = re.compile(r"^fy(\d{4})$")
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "according",
        "at",
        "by",
        "did",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "item",
        "much",
        "of",
        "on",
        "or",
        "the",
        "to",
        "was",
        "were",
        "what",
        "which",
        "with",
    }
)


def normalize_text(text: str) -> str:
    """Lowercase text and strip thousands-separators inside numbers."""
    return _COMMA_RE.sub("", text.lower())


def tokenize(text: str) -> list[str]:
    """Split normalized text into alphanumeric tokens, keeping decimals.

    Fiscal-year abbreviations like ``FY2024`` collapse to ``2024`` so they
    match heading text such as ``Fiscal Year 2024``.
    """
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(normalize_text(text)):
        fy_match = _FY_RE.match(token)
        tokens.append(fy_match.group(1) if fy_match else token)
    return tokens
