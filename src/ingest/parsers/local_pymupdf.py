"""Local PDF parser based on PyMuPDF (fitz).

Provides free, zero-key parsing for Tier B visitors and acts as the
reference baseline for Quality Gate text coverage checks.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pymupdf

from src.ingest.parsers.cleanup import clean_blocks
from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc
from src.interfaces import IParser
from src.security.secret import Secret


def count_pages(pdf_path: Path) -> int:
    """Quickly count PDF pages locally without loading document contents."""
    doc = pymupdf.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def extract_raw_reference_text(pdf_path: Path) -> str:
    """Extract plain text from all pages to serve as Quality Gate baseline."""
    doc = pymupdf.open(pdf_path)
    text_parts: list[str] = []
    try:
        for page in doc:
            text_parts.append(page.get_text("text"))
    finally:
        doc.close()
    return "\n".join(text_parts).strip()


class LocalPyMuPDFParser(IParser):
    """Free local parser that infers document structure from font metadata."""

    @property
    def name(self) -> str:
        return "local_pymupdf"

    @property
    def requires_key(self) -> bool:
        return False

    async def parse(self, file_path: Path, api_key: Secret | None = None) -> StructuredDoc:
        """Parse PDF using font-size heuristics to detect headings."""
        doc = pymupdf.open(file_path)
        raw_reference = []
        blocks: list[Block] = []

        try:
            total_pages = len(doc)

            # Pass 1: Gather font sizes across document to calibrate heading thresholds
            font_sizes: list[float] = []
            for page in doc:
                page_dict = page.get_text("dict")
                for b in page_dict.get("blocks", []):
                    if b.get("type") == 0:  # text block
                        for line in b.get("lines", []):
                            for span in line.get("spans", []):
                                text = span.get("text", "").strip()
                                if text:
                                    font_sizes.append(round(span.get("size", 10.0), 1))

            median_size = 10.0
            h1_size = 16.0
            h2_size = 13.0
            if font_sizes:
                sorted_sizes = sorted(font_sizes)
                median_size = sorted_sizes[len(sorted_sizes) // 2]
                h1_size = median_size * 1.45
                h2_size = median_size * 1.2

            # Pass 2: Extract structured blocks
            for page_idx, page in enumerate(doc, start=1):
                page_text = page.get_text("text")
                raw_reference.append(page_text)

                page_dict = page.get_text("dict")
                for b in page_dict.get("blocks", []):
                    bbox = list(b.get("bbox", [])) if "bbox" in b else None
                    if b.get("type") == 0:  # Text block
                        block_text_parts: list[str] = []
                        max_span_size = 0.0
                        is_bold = False

                        for line in b.get("lines", []):
                            line_text_parts: list[str] = []
                            for span in line.get("spans", []):
                                stext = span.get("text", "")
                                line_text_parts.append(stext)
                                size = span.get("size", 10.0)
                                if size > max_span_size:
                                    max_span_size = size
                                # Check font flags: 2=italic, 4=serif, 16=bold (or font name contains bold)
                                font_name = span.get("font", "").lower()
                                if (span.get("flags", 0) & 16) or "bold" in font_name or "black" in font_name:
                                    is_bold = True
                            block_text_parts.append(" ".join(line_text_parts))

                        block_text = "\n".join(block_text_parts).strip()
                        if not block_text:
                            continue

                        # Classify block type based on font statistics
                        if max_span_size >= h1_size:
                            b_type = BlockType.HEADING
                            level = 1
                        elif max_span_size >= h2_size or (is_bold and len(block_text) < 100 and "\n" not in block_text):
                            b_type = BlockType.HEADING
                            level = 2
                        elif block_text.startswith(("- ", "* ", "• ", "1. ", "2. ", "3. ")):
                            b_type = BlockType.LIST_ITEM
                            level = None
                        else:
                            b_type = BlockType.PARAGRAPH
                            level = None

                        blocks.append(
                            Block(
                                type=b_type,
                                text=block_text,
                                level=level,
                                page=page_idx,
                                bbox=bbox,
                                order=len(blocks),
                            )
                        )
        finally:
            doc.close()

        # Clean blocks, strip running headers/footers
        cleaned = clean_blocks(blocks, total_pages=total_pages)

        return StructuredDoc(
            doc_id=f"doc_{uuid.uuid4().hex[:12]}",
            title=file_path.stem.replace("_", " ").title(),
            page_count=total_pages,
            parser_used=self.name,
            parser_version="pymupdf-2.0",
            blocks=cleaned,
            raw_text="\n".join(raw_reference),
        )
