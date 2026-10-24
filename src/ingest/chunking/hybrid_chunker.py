"""Hybrid chunker combining structure awareness, parent-child hierarchies, and heading fusion.

Implements the IChunker interface according to architecture spec §4.4.
Produces small child chunks for high-precision vector search and
larger parent context sections for LLM answer synthesis.
"""

import hashlib

from src.ingest.chunking.heading_stack import tag_blocks_with_breadcrumbs
from src.ingest.chunking.models import (
    ChildChunk,
    ChunkingConfig,
    ChunkingResult,
    ParentChunk,
)
from src.ingest.chunking.recursive_splitter import RecursiveTokenSplitter
from src.ingest.chunking.table_splitter import split_markdown_table
from src.ingest.chunking.tokenizer import estimate_tokens
from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc
from src.interfaces import IChunker


class HybridChunker(IChunker):
    """Production hybrid chunker with recursive splitting and parent-child linking."""

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()
        self.child_splitter = RecursiveTokenSplitter(
            target_tokens=self.config.child_target_tokens,
            max_tokens=self.config.child_max_tokens,
            min_tokens=self.config.child_min_tokens,
            overlap_ratio=self.config.child_overlap,
        )

    def chunk(self, structured_doc: StructuredDoc, config: ChunkingConfig | None = None) -> ChunkingResult:
        """Chunk a StructuredDoc into linked parents and children."""
        cfg = config or self.config
        doc_id = structured_doc.doc_id
        doc_title = structured_doc.title or "Document"

        if not structured_doc.blocks:
            return ChunkingResult(doc_id=doc_id, parents=[], children=[])

        # Step 1: Structure pass - tag blocks with hierarchical breadcrumbs
        tagged_blocks = tag_blocks_with_breadcrumbs(
            structured_doc.blocks, doc_title=doc_title, prefix_max_tokens=cfg.prefix_max_tokens
        )

        # Step 2: Parent Construction - group blocks by section/heading
        raw_sections = self._group_blocks_into_sections(tagged_blocks)

        parents: list[ParentChunk] = []
        children: list[ChildChunk] = []

        global_child_index = 0

        for section_idx, (breadcrumb, section_blocks) in enumerate(raw_sections):
            parent_id = self._generate_parent_id(doc_id, section_idx, breadcrumb)

            # Build parent text and calculate page bounds
            parent_text = "\n\n".join(b.text.strip() for b in section_blocks if b.text.strip())
            parent_tokens = estimate_tokens(parent_text)
            page_start = min(b.page for b in section_blocks) if section_blocks else 1
            page_end = max(b.page for b in section_blocks) if section_blocks else 1

            parent = ParentChunk(
                parent_id=parent_id,
                doc_id=doc_id,
                breadcrumb=breadcrumb,
                text=parent_text,
                token_count=parent_tokens,
                page_start=page_start,
                page_end=page_end,
            )
            parents.append(parent)

            # Step 3: Child Construction within this parent
            section_children = self._create_children_for_section(
                doc_id=doc_id,
                parent_id=parent_id,
                breadcrumb=breadcrumb,
                blocks=section_blocks,
                cfg=cfg,
            )

            for child in section_children:
                child.chunk_index = global_child_index
                global_child_index += 1
                children.append(child)

        # Step 4: Link previous and next chunk IDs
        for i, child in enumerate(children):
            if i > 0:
                child.prev_chunk_id = children[i - 1].chunk_id
            if i < len(children) - 1:
                child.next_chunk_id = children[i + 1].chunk_id

        # Step 5: Validation
        self._validate_result(parents, children)

        return ChunkingResult(
            doc_id=doc_id,
            parents=parents,
            children=children,
            chunking_version="hybrid-v1",
        )

    def _group_blocks_into_sections(
        self, tagged_blocks: list[tuple[Block, str]]
    ) -> list[tuple[str, list[Block]]]:
        """Group blocks into sections based on lowest heading and breadcrumb changes."""
        sections: list[tuple[str, list[Block]]] = []
        current_breadcrumb: str | None = None
        current_blocks: list[Block] = []

        for block, breadcrumb in tagged_blocks:
            # Skip standalone empty headings or empty blocks
            if not block.text.strip():
                continue

            if current_breadcrumb is None:
                current_breadcrumb = breadcrumb
                current_blocks = [block]
            elif breadcrumb == current_breadcrumb:
                current_blocks.append(block)
            else:
                # Section changed
                sections.append((current_breadcrumb, current_blocks))
                current_breadcrumb = breadcrumb
                current_blocks = [block]

        if current_blocks and current_breadcrumb:
            sections.append((current_breadcrumb, current_blocks))

        return sections

    def _create_children_for_section(
        self,
        doc_id: str,
        parent_id: str,
        breadcrumb: str,
        blocks: list[Block],
        cfg: ChunkingConfig,
    ) -> list[ChildChunk]:
        """Produce child chunks from section blocks."""
        children: list[ChildChunk] = []

        # Buffer consecutive paragraph blocks for merging
        paragraph_buffer: list[Block] = []

        def flush_paragraph_buffer() -> None:
            if not paragraph_buffer:
                return

            combined_text = "\n\n".join(b.text.strip() for b in paragraph_buffer)
            page = paragraph_buffer[0].page
            bbox = paragraph_buffer[0].bbox

            # Split paragraph text recursively if needed
            split_texts = self.child_splitter.split_text(combined_text)

            for text_piece in split_texts:
                content_hash = hashlib.sha256(text_piece.encode("utf-8")).hexdigest()[:16]
                chunk_id = self._generate_child_id(doc_id, parent_id, len(children), content_hash)

                # Heading fusion: prepend breadcrumb to embedding_text
                embedding_text = f"[{breadcrumb}]\n\n{text_piece}"

                child = ChildChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    parent_id=parent_id,
                    breadcrumb=breadcrumb,
                    display_text=text_piece,
                    embedding_text=embedding_text,
                    child_tokens=estimate_tokens(text_piece),
                    chunk_index=len(children),
                    chunk_type="text",
                    page=page,
                    bbox=bbox,
                    content_hash=content_hash,
                )
                children.append(child)

            paragraph_buffer.clear()

        for block in blocks:
            if block.type == BlockType.HEADING:
                # Headings are structural metadata already captured in breadcrumbs and parents
                continue
            elif block.type == BlockType.TABLE:
                flush_paragraph_buffer()
                # Split table rows if oversized
                table_pieces = split_markdown_table(block.text, max_tokens=cfg.table_max_tokens)
                for table_piece in table_pieces:
                    content_hash = hashlib.sha256(table_piece.encode("utf-8")).hexdigest()[:16]
                    chunk_id = self._generate_child_id(doc_id, parent_id, len(children), content_hash)
                    embedding_text = f"[{breadcrumb}]\n\n{table_piece}"

                    children.append(
                        ChildChunk(
                            chunk_id=chunk_id,
                            doc_id=doc_id,
                            parent_id=parent_id,
                            breadcrumb=breadcrumb,
                            display_text=table_piece,
                            embedding_text=embedding_text,
                            child_tokens=estimate_tokens(table_piece),
                            chunk_index=len(children),
                            chunk_type="table",
                            page=block.page,
                            bbox=block.bbox,
                            content_hash=content_hash,
                        )
                    )
            elif block.type in (BlockType.CODE, BlockType.LIST_ITEM):
                flush_paragraph_buffer()
                content_hash = hashlib.sha256(block.text.encode("utf-8")).hexdigest()[:16]
                chunk_id = self._generate_child_id(doc_id, parent_id, len(children), content_hash)
                embedding_text = f"[{breadcrumb}]\n\n{block.text}"

                chunk_type_val = "code" if block.type == BlockType.CODE else "list"
                children.append(
                    ChildChunk(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        parent_id=parent_id,
                        breadcrumb=breadcrumb,
                        display_text=block.text,
                        embedding_text=embedding_text,
                        child_tokens=estimate_tokens(block.text),
                        chunk_index=len(children),
                        chunk_type=chunk_type_val,
                        page=block.page,
                        bbox=block.bbox,
                        content_hash=content_hash,
                    )
                )
            else:
                # Regular paragraph or heading block - accumulate in buffer
                paragraph_buffer.append(block)

        flush_paragraph_buffer()
        return children

    def _generate_parent_id(self, doc_id: str, section_idx: int, breadcrumb: str) -> str:
        """Deterministic parent ID based on doc and section index."""
        raw_id = f"{doc_id}:p:{section_idx}:{breadcrumb}"
        return f"p_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:12]}"

    def _generate_child_id(self, doc_id: str, parent_id: str, index: int, content_hash: str) -> str:
        """Deterministic child ID based on doc, parent, index and hash."""
        raw_id = f"{doc_id}:{parent_id}:{index}:{content_hash}"
        return f"c_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:12]}"

    def _validate_result(self, parents: list[ParentChunk], children: list[ChildChunk]) -> None:
        """Validate parent-child integrity and token constraints."""
        parent_ids = {p.parent_id for p in parents}
        seen_child_ids: set[str] = set()

        for child in children:
            if child.parent_id not in parent_ids:
                raise ValueError(f"Child {child.chunk_id} has invalid parent_id {child.parent_id}")
            if child.chunk_id in seen_child_ids:
                raise ValueError(f"Duplicate child chunk_id detected: {child.chunk_id}")
            seen_child_ids.add(child.chunk_id)
            if not child.display_text.strip():
                raise ValueError(f"Empty child chunk text for {child.chunk_id}")
