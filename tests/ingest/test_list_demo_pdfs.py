"""Demo ingest file selection prefers Apple 10-Ks."""

from pathlib import Path

from scripts.ingest_demo import DEMO_PARSER_NAME, list_demo_pdfs
from src.ingest.demo_parser import DEFAULT_DEMO_PARSER
from src.ingest.parsers.local_pymupdf import LocalPyMuPDFParser


def test_demo_parser_default_is_local_pymupdf() -> None:
    parser = LocalPyMuPDFParser()
    assert parser.name == DEMO_PARSER_NAME == DEFAULT_DEMO_PARSER
    assert parser.requires_key is False


def test_list_demo_pdfs_prefers_apple_reports(tmp_path: Path) -> None:
    (tmp_path / "notes.pdf").write_bytes(b"%PDF-1.4")
    apple = tmp_path / "Apple-Annual-Report-2025.pdf"
    apple.write_bytes(b"%PDF-1.4")
    chosen = list_demo_pdfs(tmp_path)
    assert chosen == [apple]


def test_list_demo_pdfs_falls_back_to_any_pdf(tmp_path: Path) -> None:
    other = tmp_path / "other.pdf"
    other.write_bytes(b"%PDF-1.4")
    assert list_demo_pdfs(tmp_path) == [other]
