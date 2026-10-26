"""Tests for Quality Gate sanity checks."""

from src.ingest.parsers.quality_gate import evaluate_parse_quality
from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc


def test_quality_gate_passes_clean_doc() -> None:
    blocks = [
        Block(type=BlockType.HEADING, text="Overview", level=1, page=1, order=0),
        Block(
            type=BlockType.PARAGRAPH,
            text="This is a clean paragraph with good length.",
            page=1,
            order=1,
        ),
        Block(type=BlockType.HEADING, text="Details", level=2, page=2, order=2),
        Block(
            type=BlockType.PARAGRAPH,
            text="Another paragraph detailing the system.",
            page=2,
            order=3,
        ),
    ]

    doc = StructuredDoc(
        doc_id="doc_clean",
        title="Clean Doc",
        page_count=2,
        parser_used="local_pymupdf",
        blocks=blocks,
    )

    ref_text = "Overview\nThis is a clean paragraph with good length.\nDetails\nAnother paragraph detailing the system."

    result = evaluate_parse_quality(doc, reference_text=ref_text)
    assert result.passed is True
    assert result.has_warnings is False
    assert len(result.warnings) == 0
    assert result.advice is None


def test_quality_gate_flags_low_coverage() -> None:
    blocks = [
        Block(type=BlockType.PARAGRAPH, text="Small snippet.", page=1, order=0),
    ]

    doc = StructuredDoc(
        doc_id="doc_low",
        title="Low Coverage",
        page_count=1,
        parser_used="llamaparse",
        blocks=blocks,
    )

    # Reference text is huge compared to extracted 14 characters
    ref_text = "Detailed paragraph. " * 50

    result = evaluate_parse_quality(doc, reference_text=ref_text)
    assert result.passed is True
    assert result.has_warnings is True
    assert any("Low text coverage" in w for w in result.warnings)
    assert result.advice is not None


def test_quality_gate_flags_zero_headings_in_long_doc() -> None:
    # 5 pages but no headings
    blocks = [
        Block(type=BlockType.PARAGRAPH, text="Page 1 text", page=1, order=0),
        Block(type=BlockType.PARAGRAPH, text="Page 2 text", page=2, order=1),
        Block(type=BlockType.PARAGRAPH, text="Page 3 text", page=3, order=2),
        Block(type=BlockType.PARAGRAPH, text="Page 4 text", page=4, order=3),
        Block(type=BlockType.PARAGRAPH, text="Page 5 text", page=5, order=4),
    ]

    doc = StructuredDoc(
        doc_id="doc_no_heads",
        title="No Headings",
        page_count=5,
        parser_used="local_pymupdf",
        blocks=blocks,
    )

    result = evaluate_parse_quality(doc)
    assert result.has_warnings is True
    assert any("Zero headings detected" in w for w in result.warnings)


def test_quality_gate_flags_garbled_characters() -> None:
    garbled_text = "Corrupted text \ufffd\ufffd\ufffd\ufffd\ufffd\ufffd with replacement symbols"
    blocks = [
        Block(type=BlockType.PARAGRAPH, text=garbled_text, page=1, order=0),
    ]

    doc = StructuredDoc(
        doc_id="doc_garbled",
        title="Garbled Doc",
        page_count=1,
        parser_used="local_pymupdf",
        blocks=blocks,
    )

    result = evaluate_parse_quality(doc)
    assert result.has_warnings is True
    assert any("garbled" in w.lower() for w in result.warnings)
