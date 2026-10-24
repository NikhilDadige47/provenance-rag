"""Data models and configuration for the Phase 3 chunking pipeline.

Implements parent-child schemas, heading fusion representations,
and tunable chunking parameters adhering to architecture spec §4.4.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ChunkingConfig(BaseModel):
    """Configuration parameters for the hybrid chunker."""

    child_target_tokens: int = Field(default=300, description="Target token size for children")
    child_max_tokens: int = Field(default=450, description="Hard cap on child token size")
    child_min_tokens: int = Field(default=120, description="Minimum tokens below which chunks merge")
    child_overlap: float = Field(default=0.12, description="Token overlap ratio when splitting paragraphs")

    parent_target_tokens: int = Field(default=1000, description="Target token size for parent sections")
    parent_max_tokens: int = Field(default=1500, description="Maximum token size for parents")
    fallback_parent_tokens: int = Field(default=1000, description="Target parent size for no-heading docs")

    table_max_tokens: int = Field(default=800, description="Max table tokens before row-wise splitting")
    prefix_max_tokens: int = Field(default=60, description="Cap on heading breadcrumb tokens")
    window_neighbors: int = Field(default=1, description="Adjacent child window count")


class ParentChunk(BaseModel):
    """Parent chunk containing broad context for answer synthesis."""

    parent_id: str
    doc_id: str
    breadcrumb: str
    text: str
    token_count: int
    page_start: int
    page_end: int


class ChildChunk(BaseModel):
    """Child chunk retrieved during search and embedded into vector store."""

    chunk_id: str
    doc_id: str
    parent_id: str
    breadcrumb: str
    display_text: str
    embedding_text: str
    child_tokens: int
    chunk_index: int
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None
    chunk_type: Literal["text", "table", "code", "list"] = "text"
    page: int
    bbox: list[float] | None = None
    content_hash: str


class ChunkingResult(BaseModel):
    """Complete output of the chunking pass."""

    doc_id: str
    parents: list[ParentChunk]
    children: list[ChildChunk]
    chunking_version: str = "hybrid-v1"
