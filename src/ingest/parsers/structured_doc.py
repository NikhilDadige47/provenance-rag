"""Unified document representation for all document parsers.

Normalizes raw output from LlamaParse, LandingAI, and PyMuPDF into a single,
typed block-level schema so downstream chunking never knows which parser was used.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class BlockType(StrEnum):
    """Categorized semantic block types."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    CODE = "code"
    FIGURE = "figure"
    CAPTION = "caption"


class Block(BaseModel):
    """Atomic content unit extracted from a document."""

    type: BlockType
    text: str = Field(description="Cleaned textual content (tables carry Markdown format)")
    level: int | None = Field(
        default=None,
        description="Heading level 1..6 if type is heading, otherwise None",
    )
    page: int = Field(default=1, ge=1, description="1-indexed page number")
    bbox: list[float] | None = Field(
        default=None,
        description="Bounding box [top, left, bottom, right] for coordinate grounding",
    )
    order: int = Field(default=0, ge=0, description="Sequential reading order index in document")

    @model_validator(mode="after")
    def validate_heading_level(self) -> Block:
        if self.type == BlockType.HEADING:
            if self.level is None or not (1 <= self.level <= 6):
                # Fallback to level 2 if not explicitly 1-6
                self.level = 2 if self.level is None else max(1, min(6, self.level))
        else:
            self.level = None
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("Block text cannot be empty or whitespace only.")
        return self


class StructuredDoc(BaseModel):
    """Standardized document structure used by chunkers and quality gates."""

    doc_id: str
    title: str
    page_count: int = Field(ge=1, description="Total number of pages in source document")
    parser_used: str = Field(description="Name of the parser that produced this doc")
    parser_version: str = Field(default="v1")
    blocks: list[Block] = Field(default_factory=list)
    raw_text: str | None = Field(
        default=None,
        description="Optional full reference text for quality gate checks",
    )

    def get_headings(self) -> list[Block]:
        """Return all heading blocks in reading order."""
        return [b for b in self.blocks if b.type == BlockType.HEADING]

    def get_tables(self) -> list[Block]:
        """Return all table blocks."""
        return [b for b in self.blocks if b.type == BlockType.TABLE]

    def get_blocks_for_page(self, page_number: int) -> list[Block]:
        """Return all blocks located on a specific page."""
        return [b for b in self.blocks if b.page == page_number]

    def total_text_length(self) -> int:
        """Total characters across all blocks."""
        return sum(len(b.text) for b in self.blocks)

    def validate_order(self) -> bool:
        """Verify that blocks are sequentially ordered."""
        orders = [b.order for b in self.blocks]
        return orders == sorted(orders) and len(set(orders)) == len(orders)
