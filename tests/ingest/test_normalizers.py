"""Tests for LlamaParse and Landing AI normalizers."""

from src.ingest.parsers.landingai import LandingAINormalizer
from src.ingest.parsers.llamaparse import LlamaParseNormalizer
from src.ingest.parsers.structured_doc import BlockType


def test_llamaparse_normalizer_markdown() -> None:
    raw_markdown = """
# System Architecture

This is the introductory paragraph.

| Component | Status |
|---|---|
| Chunker | Ready |
| Embedder | Active |

- Feature 1
- Feature 2

--- [Page 2] ---

## Secondary Section

Detailed description on page two.
```python
def example():
    return True
```
"""
    blocks = LlamaParseNormalizer.parse_markdown_to_blocks(raw_markdown)

    types = [b.type for b in blocks]
    assert BlockType.HEADING in types
    assert BlockType.PARAGRAPH in types
    assert BlockType.TABLE in types
    assert BlockType.LIST_ITEM in types
    assert BlockType.CODE in types

    # Page tracking
    h1 = [b for b in blocks if b.type == BlockType.HEADING and b.level == 1][0]
    assert h1.page == 1
    assert h1.text == "System Architecture"

    h2 = [b for b in blocks if b.type == BlockType.HEADING and b.level == 2][0]
    assert h2.page == 2
    assert h2.text == "Secondary Section"


def test_landingai_normalizer_chunks() -> None:
    payload = {
        "chunks": [
            {
                "type": "text",
                "markdown": "# Financial Highlights",
                "grounding": {"page": 1, "box": [10.0, 20.0, 50.0, 200.0]},
            },
            {
                "type": "table",
                "markdown": "| Revenue | $10M |\n| Net | $2M |",
                "grounding": {"page": 1, "box": [60.0, 20.0, 150.0, 300.0]},
            },
            {
                "type": "text",
                "markdown": "Overall company margins improved substantially.",
                "grounding": {"page": 2, "box": [15.0, 20.0, 45.0, 250.0]},
            },
        ]
    }

    blocks = LandingAINormalizer.parse_payload_to_blocks(payload)

    assert len(blocks) == 3
    assert blocks[0].type == BlockType.HEADING
    assert blocks[0].level == 1
    assert blocks[0].bbox == [10.0, 20.0, 50.0, 200.0]

    assert blocks[1].type == BlockType.TABLE
    assert blocks[2].type == BlockType.PARAGRAPH
    assert blocks[2].page == 2


def test_llamaparse_fixture_file() -> None:
    """Verify LlamaParse normalizer against raw fixture file on disk."""
    import pathlib

    fixture_path = pathlib.Path("tests/fixtures/llamaparse_sample.md")
    assert fixture_path.exists(), "LlamaParse fixture file missing"

    content = fixture_path.read_text(encoding="utf-8")
    blocks = LlamaParseNormalizer.parse_markdown_to_blocks(content)

    assert len(blocks) > 0
    headings = [b for b in blocks if b.type == BlockType.HEADING]
    tables = [b for b in blocks if b.type == BlockType.TABLE]
    assert len(headings) >= 2
    assert len(tables) >= 1
    assert headings[0].text == "System Architecture Overview"
    assert headings[1].page == 2


def test_landingai_fixture_file() -> None:
    """Verify Landing AI normalizer against raw JSON fixture on disk."""
    import json
    import pathlib

    fixture_path = pathlib.Path("tests/fixtures/landingai_sample.json")
    assert fixture_path.exists(), "Landing AI fixture file missing"

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    blocks = LandingAINormalizer.parse_payload_to_blocks(payload)

    assert len(blocks) == 3
    assert blocks[0].type == BlockType.HEADING
    assert blocks[0].text == "Financial Highlights 2025"
    assert blocks[0].bbox == [10.0, 20.0, 45.0, 220.0]
    assert blocks[1].type == BlockType.TABLE
    assert blocks[2].type == BlockType.PARAGRAPH
