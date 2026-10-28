"""Unit tests for golden-set hit matching."""

from eval.models import EvalItem
from eval.scoring import chunk_hits_item, documents_match, rank_hits
from src.retrieval.search import RetrievedChunk


def _chunk(**kwargs) -> RetrievedChunk:
    defaults = {
        "chunk_id": "c1",
        "doc_id": "Apple-Annual-Report-2023.pdf",
        "parent_id": "p1",
        "title": "Apple",
        "breadcrumb": "FY2023 > Operations",
        "page": 34,
        "bbox": None,
        "display_text": "Total net sales were $383,285 million.",
        "embedding_text": "[FY2023]\n\nTotal net sales were $383,285 million.",
        "score": 0.9,
    }
    defaults.update(kwargs)
    return RetrievedChunk(**defaults)


def _item(**kwargs) -> EvalItem:
    defaults = {
        "id": "fact_01",
        "category": "direct_fact",
        "question": "What was Apple's total net sales in fiscal year 2023?",
        "expected_doc": "Apple-Annual-Report-2023.pdf",
        "expected_page": 34,
        "expected_answer": "$383,285 million",
        "keywords": ["383,285", "net sales"],
        "is_not_found": False,
    }
    defaults.update(kwargs)
    return EvalItem(**defaults)


def test_documents_match_on_filename() -> None:
    assert documents_match("Apple-Annual-Report-2023.pdf", "Apple-Annual-Report-2023.pdf")
    assert documents_match("demo/Apple-Annual-Report-2023.pdf", "Apple-Annual-Report-2023.pdf")
    assert not documents_match("Apple-Annual-Report-2024.pdf", "Apple-Annual-Report-2023.pdf")


def test_chunk_hits_require_doc_page_and_keyword() -> None:
    item = _item()
    assert chunk_hits_item(_chunk(), item)
    assert not chunk_hits_item(_chunk(page=1), item)
    assert not chunk_hits_item(_chunk(doc_id="Apple-Annual-Report-2024.pdf"), item)
    assert not chunk_hits_item(_chunk(display_text="unrelated", embedding_text="unrelated"), item)


def test_rank_hits_uses_first_matching_rank() -> None:
    item = _item()
    miss = _chunk(chunk_id="c0", page=1, display_text="intro", embedding_text="intro")
    hit = _chunk(chunk_id="c1")
    hit_at_5, hit_at_10, mrr = rank_hits([miss, miss, hit], item)
    assert hit_at_5 is True
    assert hit_at_10 is True
    assert mrr == 1.0 / 3
