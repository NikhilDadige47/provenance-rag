"""Tests for ContextExpander parent/window context expansion and token budget."""

from unittest.mock import MagicMock

from src.retrieval.expansion import ContextExpander
from src.retrieval.search import RetrievedChunk


def test_context_expander_parent_retrieval():
    """Verify expander retrieves full parent when parent tokens <= max."""
    mock_db = MagicMock()
    mock_db.get_parent.return_value = {
        "parent_id": "p1",
        "doc_id": "d1",
        "breadcrumb": "Finance > Revenue",
        "text": "Full parent passage text discussing quarterly results and growth projections.",
        "token_count": 150,
        "page_start": 3,
        "page_end": 3,
    }

    expander = ContextExpander(db=mock_db, parent_expand_max=1200, context_budget=3500)
    chunk = RetrievedChunk(
        chunk_id="c1",
        doc_id="d1",
        parent_id="p1",
        title="Annual Report",
        breadcrumb="Finance > Revenue",
        page=3,
        bbox=None,
        display_text="child snippet",
        embedding_text="child embedding text",
        score=0.9,
    )

    res = expander.expand([chunk], scope="demo")
    assert len(res.passages) == 1
    assert res.passages[0].is_parent_expanded is True
    assert "Full parent passage text" in res.passages[0].text
    mock_db.get_parent.assert_called_once_with("p1", scope="demo")


def test_context_expander_deduplicates_same_parent():
    """Verify multiple chunks with identical parent_id result in one expanded passage."""
    mock_db = MagicMock()
    mock_db.get_parent.return_value = {
        "parent_id": "p_shared",
        "doc_id": "d1",
        "breadcrumb": "Overview",
        "text": "Shared parent context for both child chunks.",
        "token_count": 100,
        "page_start": 1,
        "page_end": 1,
    }

    expander = ContextExpander(db=mock_db)
    chunk1 = RetrievedChunk(
        chunk_id="c1",
        doc_id="d1",
        parent_id="p_shared",
        title="Doc",
        breadcrumb="Overview",
        page=1,
        bbox=None,
        display_text="Piece 1",
        embedding_text="Piece 1",
        score=0.9,
    )
    chunk2 = RetrievedChunk(
        chunk_id="c2",
        doc_id="d1",
        parent_id="p_shared",
        title="Doc",
        breadcrumb="Overview",
        page=1,
        bbox=None,
        display_text="Piece 2",
        embedding_text="Piece 2",
        score=0.8,
    )

    res = expander.expand([chunk1, chunk2], scope="demo")
    assert len(res.passages) == 1
    assert mock_db.get_parent.call_count == 1


def test_context_expander_skips_duplicate_child_text():
    """Overlapping rerank hits of the same snippet must not become two passages."""
    mock_db = MagicMock()
    mock_db.get_parent.return_value = None
    expander = ContextExpander(db=mock_db)
    same_text = "The Company's total net sales were $383.3 billion during 2023."
    chunks = [
        RetrievedChunk(
            chunk_id=f"c{i}",
            doc_id="d1",
            parent_id=f"p{i}",
            title="Apple-Annual-Report-2023",
            breadcrumb="Item 7",
            page=1,
            bbox=None,
            display_text=same_text,
            embedding_text=same_text,
            score=0.9 - i * 0.05,
        )
        for i in range(2)
    ]
    res = expander.expand(chunks, scope="demo")
    assert len(res.passages) == 1
