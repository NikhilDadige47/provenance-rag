"""Tests for citation extraction, grounding verification, and hallucination detection."""

from src.generation.citations import audit_citations, extract_citation_indices
from src.retrieval.expansion import ExpandedContextPassage


def test_extract_citation_indices():
    """Verify bracketed citation extraction handles single and multiple indices."""
    text = "According to [1], the revenue grew significantly, while costs fell as noted in [2, 3]."
    indices = extract_citation_indices(text)
    assert indices == [1, 2, 3]


def test_audit_citations_detects_hallucinations():
    """Verify cited numbers outside the available passages are flagged as invalid."""
    passages = [
        ExpandedContextPassage(
            passage_id="p1", doc_id="d1", title="Report", breadcrumb="Finance",
            page=1, text="Revenue was $10M.", token_count=10, is_parent_expanded=True, source_chunk_ids=["c1"]
        ),
        ExpandedContextPassage(
            passage_id="p2", doc_id="d1", title="Report", breadcrumb="Costs",
            page=2, text="Costs were $6M.", token_count=10, is_parent_expanded=True, source_chunk_ids=["c2"]
        ),
    ]

    answer = "Revenue reached $10M [1], and future outlook was optimistic [5]."
    audit = audit_citations(answer, passages)

    assert audit.raw_citations == [1, 5]
    assert audit.valid_citations == [1]
    assert audit.invalid_citations == [5]
    assert audit.is_grounded is False
    assert len(audit.sources) == 1
    assert audit.sources[0].citation_index == 1
    assert audit.sources[0].title == "Report"
    assert audit.sources[0].page == 1


def test_audit_citations_valid_grounded():
    """Verify completely grounded citations pass audit."""
    passages = [
        ExpandedContextPassage(
            passage_id="p1", doc_id="d1", title="Report", breadcrumb="Finance",
            page=1, text="Revenue was $10M.", token_count=10, is_parent_expanded=True, source_chunk_ids=["c1"]
        ),
    ]

    answer = "Revenue was $10M [1]."
    audit = audit_citations(answer, passages)

    assert audit.valid_citations == [1]
    assert audit.invalid_citations == []
    assert audit.is_grounded is True
