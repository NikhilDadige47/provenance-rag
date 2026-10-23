"""Tests for text normalization and header/footer removal."""

from src.ingest.parsers.cleanup import (
    clean_blocks,
    fix_hyphenation,
    normalize_whitespace_and_unicode,
    remove_repeated_headers_and_footers,
)
from src.ingest.parsers.structured_doc import Block, BlockType


def test_fix_hyphenation() -> None:
    text = "This is a multi-\nprocess and fully au-\n  tonomous system."
    fixed = fix_hyphenation(text)
    assert "multiprocess" in fixed
    assert "autonomous" in fixed


def test_normalize_whitespace_and_unicode() -> None:
    text = "Hello\u00a0world!   Extra   spaces.\n\n\n\u200bClean  me."
    normalized = normalize_whitespace_and_unicode(text)
    assert "Hello world!" in normalized
    assert "Extra spaces." in normalized
    assert "Clean me." in normalized


def test_remove_repeated_headers_and_footers() -> None:
    # 3 pages with same running header "Confidential Report"
    blocks = [
        Block(type=BlockType.PARAGRAPH, text="Confidential Report", page=1, order=0),
        Block(type=BlockType.PARAGRAPH, text="Page 1 body content", page=1, order=1),
        Block(type=BlockType.PARAGRAPH, text="Page 1", page=1, order=2),
        Block(type=BlockType.PARAGRAPH, text="Confidential Report", page=2, order=3),
        Block(type=BlockType.PARAGRAPH, text="Page 2 body content", page=2, order=4),
        Block(type=BlockType.PARAGRAPH, text="Page 2", page=2, order=5),
        Block(type=BlockType.PARAGRAPH, text="Confidential Report", page=3, order=6),
        Block(type=BlockType.PARAGRAPH, text="Page 3 body content", page=3, order=7),
    ]

    cleaned = remove_repeated_headers_and_footers(blocks, total_pages=3, min_page_frequency=0.4)

    texts = [b.text for b in cleaned]
    assert "Confidential Report" not in texts
    assert "Page 1" not in texts
    assert "Page 1 body content" in texts
    assert "Page 2 body content" in texts
    assert "Page 3 body content" in texts


def test_clean_blocks_reorders_indices() -> None:
    blocks = [
        Block(type=BlockType.PARAGRAPH, text="First  block", page=1, order=10),
        Block(type=BlockType.PARAGRAPH, text="Second   block", page=1, order=20),
    ]
    cleaned = clean_blocks(blocks, total_pages=1)
    assert len(cleaned) == 2
    assert cleaned[0].order == 0
    assert cleaned[1].order == 1
    assert cleaned[0].text == "First block"
    assert cleaned[1].text == "Second block"
