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

# [1], [1, 2], 【1】, and provider footnotes like 【1†L1-L4】
_BRACKET_RE = re.compile(r"(?:\[|【)([^\]】]{1,80})(?:\]|】)")
_LEADING_INT_RE = re.compile(r"^\s*(\d+)")
_MARKER_RE = re.compile(
    r"(?:\[|【)\s*(\d+(?:\s*,\s*\d+)*)(?:\s*[†‡][^\]】]*)?\s*(?:\]|】)"
)


def normalize_citation_markers(text: str) -> str:
    """Rewrite provider footnotes such as 【1†L1-L4】 into clickable [1] markers."""

    def _replace(match: re.Match[str]) -> str:
        nums = [part.strip() for part in match.group(1).split(",") if part.strip().isdigit()]
        if not nums:
            return match.group(0)
        return "".join(f"[{n}]" for n in nums)

    return _MARKER_RE.sub(_replace, text)


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
    """Find citation integers in [1], [1, 2], 【1】, or 【1†L1-L4】 footnote form."""
    indices: set[int] = set()
    for match in _BRACKET_RE.finditer(text):
        inner = match.group(1)
        for part in inner.split(","):
            leading = _LEADING_INT_RE.match(part)
            if leading:
                indices.add(int(leading.group(1)))
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
                    text_snippet=passage.text,
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
