"""Citation validator and provenance metadata enricher.

Implements roadmap P4-T6 & architecture §5:
- Extracts bracketed citation references from the generated response (e.g. [1], [2], [1, 3])
- Verifies every cited passage number exists within the active context
- Flags or removes fabricated/hallucinated citation IDs
- Enriches valid citations with document title, page numbers, breadcrumb path, and bounding boxes
"""

import re
from dataclasses import dataclass

from src.retrieval.expansion import ExpandedContextPassage

CITATION_PATTERN = re.compile(r"(?:\[|【)(\d+(?:\s*,\s*\d+)*)(?:\]|】)")


@dataclass
class VerifiedSource:
    """Provenance metadata for an audited citation."""

    citation_index: int
    passage_id: str
    doc_id: str
    title: str
    breadcrumb: str
    page: int
    text_snippet: str
    is_parent_expanded: bool


@dataclass
class CitationAuditResult:
    """The result of auditing citations in generated text."""

    raw_citations: list[int]
    valid_citations: list[int]
    invalid_citations: list[int]
    sources: list[VerifiedSource]
    is_grounded: bool


def extract_citation_indices(text: str) -> list[int]:
    """Find all citation integers referenced in bracket notation (e.g., [1], [1, 2])."""
    indices: set[int] = set()
    for match in CITATION_PATTERN.finditer(text):
        group = match.group(1)
        for part in group.split(","):
            part_str = part.strip()
            if part_str.isdigit():
                indices.add(int(part_str))
    return sorted(indices)


def audit_citations(
    generated_text: str,
    passages: list[ExpandedContextPassage],
) -> CitationAuditResult:
    """Verify citations in the generated answer against the context passages.

    Args:
        generated_text: Complete LLM output.
        passages: Ordered list of context passages provided in the prompt (1-indexed).

    Returns:
        CitationAuditResult detailing valid citations and enriched source metadata.
    """
    raw_indices = extract_citation_indices(generated_text)
    num_passages = len(passages)

    valid_indices: list[int] = []
    invalid_indices: list[int] = []
    sources: list[VerifiedSource] = []

    for idx in raw_indices:
        # Passages in prompt are 1-indexed: [1] corresponds to passages[0]
        if 1 <= idx <= num_passages:
            valid_indices.append(idx)
            passage = passages[idx - 1]
            sources.append(
                VerifiedSource(
                    citation_index=idx,
                    passage_id=passage.passage_id,
                    doc_id=passage.doc_id,
                    title=passage.title,
                    breadcrumb=passage.breadcrumb,
                    page=passage.page,
                    text_snippet=passage.text[:200] + ("..." if len(passage.text) > 200 else ""),
                    is_parent_expanded=passage.is_parent_expanded,
                )
            )
        else:
            invalid_indices.append(idx)

    # Answer is considered grounded if at least one citation exists and no hallucinations occurred
    is_grounded = bool(valid_indices) and len(invalid_indices) == 0

    return CitationAuditResult(
        raw_citations=raw_indices,
        valid_citations=valid_indices,
        invalid_citations=invalid_indices,
        sources=sources,
        is_grounded=is_grounded,
    )
