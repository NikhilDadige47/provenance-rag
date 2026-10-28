"""Hit matching for golden-set evaluation (document + page + keywords)."""

from __future__ import annotations

from eval.models import EvalItem
from eval.text_utils import normalize_text
from src.retrieval.search import RetrievedChunk


def documents_match(actual_doc: str, expected_doc: str | None) -> bool:
    """True when payload doc_id refers to the same file as the expected filename."""
    if not expected_doc:
        return True
    actual = actual_doc.replace("\\", "/").rsplit("/", maxsplit=1)[-1].lower()
    expected = expected_doc.replace("\\", "/").rsplit("/", maxsplit=1)[-1].lower()
    return actual == expected


def chunk_hits_item(chunk: RetrievedChunk, item: EvalItem) -> bool:
    """A retrieved chunk is a hit when doc, page, and at least one keyword align."""
    if item.is_not_found or item.expected_page is None:
        return False
    if not documents_match(chunk.doc_id, item.expected_doc):
        return False
    if chunk.page != item.expected_page:
        return False
    if not item.keywords:
        return True
    haystack = normalize_text(f"{chunk.display_text} {chunk.embedding_text}")
    return any(normalize_text(keyword) in haystack for keyword in item.keywords)


def rank_hits(chunks: list[RetrievedChunk], item: EvalItem) -> tuple[bool, bool, float]:
    """Return (hit@5, hit@10, reciprocal_rank) over a ranked candidate list."""
    hit_at_5 = False
    hit_at_10 = False
    reciprocal_rank = 0.0
    for idx, chunk in enumerate(chunks):
        if not chunk_hits_item(chunk, item):
            continue
        if idx < 5:
            hit_at_5 = True
        if idx < 10:
            hit_at_10 = True
        if reciprocal_rank == 0.0:
            reciprocal_rank = 1.0 / (idx + 1)
        break
    return hit_at_5, hit_at_10, reciprocal_rank
