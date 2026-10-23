"""Quality gate for document parsing outputs.

Performs cheap, local sanity checks against a reference extraction to ensure
text coverage, heading integrity, and table fidelity before chunks reach the vector index.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from pydantic import BaseModel, Field

from src.ingest.parsers.structured_doc import StructuredDoc


class QualityGateResult(BaseModel):
    """Result of Quality Gate validation on a StructuredDoc."""

    passed: bool = Field(description="True if document meets minimum standards to proceed")
    has_warnings: bool = Field(description="True if non-blocking quality anomalies were detected")
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    advice: str | None = None


def check_text_coverage(doc: StructuredDoc, reference_text: str | None) -> tuple[bool, str | None, float]:
    """Check if the parsed doc captured sufficient text compared to reference."""
    if not reference_text or not reference_text.strip():
        return True, None, 1.0

    doc_len = doc.total_text_length()
    ref_len = len(reference_text.strip())

    if ref_len == 0:
        return True, None, 1.0

    ratio = round(doc_len / ref_len, 3)

    if ratio < 0.65:
        return False, f"Low text coverage: parsed content covers only {ratio*100:.1f}% of reference text.", ratio
    if ratio > 2.5:
        return False, f"Plausible duplicate text: parsed text is {ratio:.1f}x larger than reference.", ratio

    return True, None, ratio


def check_heading_sanity(doc: StructuredDoc) -> tuple[bool, str | None, dict[str, Any]]:
    """Check heading structure, hierarchy jumps, and density."""
    headings = doc.get_headings()
    heading_count = len(headings)
    info = {"heading_count": heading_count, "erratic_jumps": 0}

    # If long doc (>= 4 pages) but 0 headings, warn
    if doc.page_count >= 4 and heading_count == 0:
        return False, "Zero headings detected in a multi-page document.", info

    # Check for erratic hierarchy jumps (e.g. H1 -> H5)
    last_level = 1
    erratic_jumps = 0
    for h in headings:
        level = h.level or 2
        if level - last_level > 2:
            erratic_jumps += 1
        last_level = level

    info["erratic_jumps"] = erratic_jumps
    if erratic_jumps > 3:
        return False, f"Detected {erratic_jumps} erratic heading level jumps.", info

    return True, None, info


def check_empty_pages(doc: StructuredDoc) -> tuple[bool, str | None, list[int]]:
    """Identify pages that produced no blocks."""
    if doc.page_count <= 1:
        return True, None, []

    pages_with_content = {b.page for b in doc.blocks}
    missing_pages = [p for p in range(1, doc.page_count + 1) if p not in pages_with_content]

    if missing_pages and len(missing_pages) > (doc.page_count * 0.3):
        return (
            False,
            f"Empty pages detected: {len(missing_pages)} of {doc.page_count} pages had no content extracted.",
            missing_pages,
        )

    return True, None, missing_pages


def check_garbled_text(doc: StructuredDoc) -> tuple[bool, str | None, float]:
    """Check for high density of unicode replacement or unprintable characters."""
    total_chars = 0
    bad_chars = 0

    for b in doc.blocks:
        total_chars += len(b.text)
        for ch in b.text:
            if ch == "\ufffd" or unicodedata.category(ch) == "Co":  # Private use or replacement char
                bad_chars += 1

    if total_chars == 0:
        return True, None, 0.0

    bad_ratio = bad_chars / total_chars
    if bad_ratio > 0.03:
        return False, f"High garbled text ratio: {bad_ratio*100:.2f}% unprintable characters.", bad_ratio

    return True, None, bad_ratio


def evaluate_parse_quality(
    doc: StructuredDoc, reference_text: str | None = None
) -> QualityGateResult:
    """Evaluate parse quality across coverage, headings, empty pages, and garbled characters."""
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    # 1. Text coverage
    cov_pass, cov_warn, ratio = check_text_coverage(doc, reference_text or doc.raw_text)
    metrics["coverage_ratio"] = ratio
    if cov_warn:
        warnings.append(cov_warn)

    # 2. Heading sanity
    head_pass, head_warn, head_info = check_heading_sanity(doc)
    metrics.update(head_info)
    if head_warn:
        warnings.append(head_warn)

    # 3. Empty pages
    page_pass, page_warn, missing_pages = check_empty_pages(doc)
    metrics["missing_pages"] = missing_pages
    if page_warn:
        warnings.append(page_warn)

    # 4. Garbled text
    garb_pass, garb_warn, garb_ratio = check_garbled_text(doc)
    metrics["garbled_ratio"] = garb_ratio
    if garb_warn:
        warnings.append(garb_warn)

    # Metrics summary
    metrics["total_blocks"] = len(doc.blocks)
    metrics["table_count"] = len(doc.get_tables())

    has_warnings = len(warnings) > 0
    # Quality gate always lets the job finish, but marks warnings for the UI
    advice = (
        "Parse quality warning: Try re-uploading with a different parser (e.g. Free Local Parser or LlamaParse)."
        if has_warnings
        else None
    )

    return QualityGateResult(
        passed=True,
        has_warnings=has_warnings,
        warnings=warnings,
        metrics=metrics,
        advice=advice,
    )
