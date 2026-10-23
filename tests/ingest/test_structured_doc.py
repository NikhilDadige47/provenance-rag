"""Tests for Block and StructuredDoc schemas."""

import pytest

from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc


def test_block_creation_and_validation() -> None:
    # Heading requires level 1-6
    h = Block(type=BlockType.HEADING, text="Architecture", level=1, page=1, order=0)
    assert h.type == BlockType.HEADING
    assert h.level == 1

    # Paragraph forces level to None
    p = Block(type=BlockType.PARAGRAPH, text="Sample text", level=3, page=1, order=1)
    assert p.level is None

    # Empty text raises ValueError
    with pytest.raises(ValueError):
        Block(type=BlockType.PARAGRAPH, text="   ", page=1, order=2)


def test_structured_doc_helpers() -> None:
    blocks = [
        Block(type=BlockType.HEADING, text="Section 1", level=1, page=1, order=0),
        Block(type=BlockType.PARAGRAPH, text="Content 1", page=1, order=1),
        Block(type=BlockType.TABLE, text="| A | B |\n|---|---|\n| 1 | 2 |", page=2, order=2),
        Block(type=BlockType.HEADING, text="Section 2", level=2, page=2, order=3),
    ]

    doc = StructuredDoc(
        doc_id="doc_test_123",
        title="Test Document",
        page_count=2,
        parser_used="test_parser",
        blocks=blocks,
    )

    assert len(doc.get_headings()) == 2
    assert len(doc.get_tables()) == 1
    assert len(doc.get_blocks_for_page(1)) == 2
    assert len(doc.get_blocks_for_page(2)) == 2
    assert doc.validate_order() is True
