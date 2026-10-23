"""Tests for local PyMuPDF parser and page counting."""

from pathlib import Path

import pymupdf
import pytest

from src.ingest.parsers.local_pymupdf import (
    LocalPyMuPDFParser,
    count_pages,
    extract_raw_reference_text,
)


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a minimal real PDF using PyMuPDF for testing."""
    pdf_path = tmp_path / "sample_report.pdf"
    doc = pymupdf.open()

    # Page 1
    page1 = doc.new_page()
    page1.insert_text((50, 70), "Quarterly Financial Overview", fontsize=18)
    page1.insert_text((50, 120), "Company revenue increased significantly this fiscal year.", fontsize=11)
    page1.insert_text((50, 160), "Key Operational Highlights", fontsize=14)
    page1.insert_text((50, 200), "- Expanded infrastructure capacity", fontsize=11)

    # Page 2
    page2 = doc.new_page()
    page2.insert_text((50, 70), "Future Outlook", fontsize=18)
    page2.insert_text((50, 120), "Projected sustained growth across all customer segments.", fontsize=11)

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_count_pages(sample_pdf_path: Path) -> None:
    pages = count_pages(sample_pdf_path)
    assert pages == 2


def test_extract_raw_reference_text(sample_pdf_path: Path) -> None:
    raw = extract_raw_reference_text(sample_pdf_path)
    assert "Quarterly Financial Overview" in raw
    assert "Future Outlook" in raw


@pytest.mark.asyncio
async def test_local_pymupdf_parser(sample_pdf_path: Path) -> None:
    parser = LocalPyMuPDFParser()
    assert parser.name == "local_pymupdf"
    assert parser.requires_key is False

    doc = await parser.parse(sample_pdf_path)

    assert doc.page_count == 2
    assert doc.parser_used == "local_pymupdf"
    assert len(doc.blocks) >= 3

    # Check detected headings
    headings = doc.get_headings()
    assert len(headings) >= 1
    heading_texts = [h.text for h in headings]
    assert any("Quarterly Financial Overview" in ht or "Future Outlook" in ht for ht in heading_texts)
