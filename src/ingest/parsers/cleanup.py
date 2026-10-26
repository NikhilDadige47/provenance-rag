"""Text and block cleanup pipeline for document parsers.

Normalizes whitespace, removes hyphenated line breaks, drops empty blocks,
and removes repeated running headers and footers across pages.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from src.ingest.parsers.structured_doc import Block, BlockType

# Regex for hyphenated words across line boundaries: e.g. "con-\nnected" -> "connected"
_HYPHEN_BREAK_RE = re.compile(r"(\b[a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,}\b)")

# Match standalone page number patterns like "Page 1 of 10" or "- 4 -"
_PAGE_NUMBER_RE = re.compile(r"^(?:page\s+\d+(?:\s+of\s+\d+)?|-?\s*\d+\s*-?)$", re.IGNORECASE)


def fix_hyphenation(text: str) -> str:
    """Join words broken across lines by hyphens."""
    return _HYPHEN_BREAK_RE.sub(r"\1\2", text)


def normalize_whitespace_and_unicode(text: str) -> str:
    """Normalize unicode spaces and characters, stripping redundant blank spaces."""
    if not text:
        return ""
    # Normalize unicode to NFKC (Normal Form KC)
    normalized = unicodedata.normalize("NFKC", text)
    # Replace non-breaking spaces and zero-width spaces with regular space
    normalized = normalized.replace("\u00a0", " ").replace("\u200b", "")
    # Remove control characters except tab and newline
    normalized = "".join(
        ch for ch in normalized if ch in "\t\n\r" or unicodedata.category(ch)[0] != "C"
    )
    # Clean up multi-space lines while preserving intentional line breaks
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
    return "\n".join(lines).strip()


def remove_repeated_headers_and_footers(
    blocks: list[Block], total_pages: int, min_page_frequency: float = 0.4
) -> list[Block]:
    """Identify and drop running headers and footers repeated across pages.

    Only applies if the document has 3 or more pages.
    """
    if total_pages < 3 or not blocks:
        return blocks

    # Collect first and last text snippets on each page
    header_candidate_texts: list[str] = []
    footer_candidate_texts: list[str] = []

    blocks_by_page: dict[int, list[Block]] = {}
    for b in blocks:
        blocks_by_page.setdefault(b.page, []).append(b)

    for page_blocks in blocks_by_page.values():
        if not page_blocks:
            continue
        first_text = page_blocks[0].text.strip().lower()
        last_text = page_blocks[-1].text.strip().lower()
        # Only short snippets (< 120 chars) are plausible headers/footers
        if len(first_text) < 120:
            header_candidate_texts.append(first_text)
        if len(last_text) < 120:
            footer_candidate_texts.append(last_text)

    header_counts = Counter(header_candidate_texts)
    footer_counts = Counter(footer_candidate_texts)

    threshold = max(2, int(total_pages * min_page_frequency))

    repeated_headers = {text for text, count in header_counts.items() if count >= threshold}
    repeated_footers = {text for text, count in footer_counts.items() if count >= threshold}

    filtered_blocks: list[Block] = []
    for b in blocks:
        norm_text = b.text.strip().lower()
        # Drop standalone page numbers
        if _PAGE_NUMBER_RE.match(norm_text):
            continue
        # Drop repeated running headers / footers
        if norm_text in repeated_headers or norm_text in repeated_footers:
            continue
        filtered_blocks.append(b)

    return filtered_blocks


def clean_blocks(blocks: list[Block], total_pages: int) -> list[Block]:
    """Clean all blocks, remove headers/footers, and re-order sequential indices."""
    cleaned: list[Block] = []

    for block in blocks:
        clean_text = normalize_whitespace_and_unicode(block.text)
        clean_text = fix_hyphenation(clean_text)

        if not clean_text:
            continue  # Drop empty blocks

        # Copy block with cleaned text
        cleaned.append(
            Block(
                type=block.type,
                text=clean_text,
                level=block.level if block.type == BlockType.HEADING else None,
                page=block.page,
                bbox=block.bbox,
                order=0,  # Will be re-indexed below
            )
        )

    # Filter running headers and footers
    filtered = remove_repeated_headers_and_footers(cleaned, total_pages=total_pages)

    # Re-index reading order sequentially
    for idx, b in enumerate(filtered):
        b.order = idx

    return filtered
