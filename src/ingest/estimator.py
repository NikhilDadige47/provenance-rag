"""Pre-flight PDF estimator and credit calculator.

Runs locally via PyMuPDF in RAM at $0 cost before making any external API call.
Enforces Gate 0 (§5 of token-engineering-guide.md):
- Digital text layer detection vs scanned image detection
- Output character estimation (with markdown expansion factor)
- Landing AI model/tier route selection (Verity vs Pro)
- Worst-case credit reservation calculation
"""

from __future__ import annotations

from typing import Any

import pymupdf

from src.security.credit_config import (
    LANDING_RATES,
    LLAMA_CREDITS_PER_PAGE,
    MD_OVERHEAD,
    SCANNED_CHARS_PER_PAGE,
    VISITOR_ALLOWANCE,
    ceil_tenth,
)


class InputRejectedError(Exception):
    """Raised when an uploaded document violates Gate 0 bounds."""


def analyse_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    """Inspect PDF structure, pages, and digital vs scanned text in-memory.

    Raises:
        InputRejectedError: If PDF is encrypted, empty, or exceeds page bounds.
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise InputRejectedError(f"Malformed or unreadable PDF: {exc}") from exc

    try:
        if doc.is_encrypted:
            raise InputRejectedError("PDF is encrypted or password-protected.")
        if doc.page_count == 0:
            raise InputRejectedError("PDF contains 0 readable pages.")
        if doc.page_count > VISITOR_ALLOWANCE["max_pages_doc"]:
            raise InputRejectedError(
                f"PDF has {doc.page_count} pages, exceeding the {VISITOR_ALLOWANCE['max_pages_doc']}-page limit."
            )

        chars = 0
        digital_pages = 0

        for page in doc:
            text = page.get_text().strip()
            char_count = len(text)
            if char_count > 100:
                digital_pages += 1
                chars += int(char_count * MD_OVERHEAD)
            else:
                chars += SCANNED_CHARS_PER_PAGE

        is_digital = (digital_pages / doc.page_count) >= 0.8 if doc.page_count > 0 else True

        return {
            "pages": doc.page_count,
            "est_chars": chars,
            "digital": is_digital,
            "digital_pages": digital_pages,
            "scanned_pages": doc.page_count - digital_pages,
        }
    finally:
        doc.close()


def landing_route(info: dict[str, Any]) -> tuple[str, str]:
    """Select Landing AI model and tier based on document characteristics.

    Digital documents route to Verity Standard (~3x cheaper).
    Scanned documents route to Pro Standard.
    """
    if info.get("digital", True):
        return ("verity", "standard")
    return ("pro", "standard")


def landing_units(info: dict[str, Any]) -> int:
    """Compute required Landing AI credit reservation in integer tenths of a credit."""
    model, tier = landing_route(info)
    rate = LANDING_RATES[(model, tier)]
    pages = info.get("pages", 1)
    chars = info.get("est_chars", 2000)

    # Per-page rate + output character rate (per 1,000 chars)
    raw_credits = pages * rate.page + (chars / 1000.0) * rate.per_1k
    rounded_credit = ceil_tenth(raw_credits)
    # Stored as integer tenths (e.g., 2.1 credits = 21 units)
    return int(round(rounded_credit * 10))


def llama_units(info: dict[str, Any], tier: str = "cost_effective") -> int:
    """Compute required LlamaParse credit reservation."""
    rate = LLAMA_CREDITS_PER_PAGE.get(tier, 3)
    return int(info.get("pages", 1) * rate)
