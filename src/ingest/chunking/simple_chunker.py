"""Fixed-size chunker with no document structure or heading fusion.

Used as the simple-chunking baseline in ablation studies. Packs blocks in
reading order into token-bounded windows and sets embedding_text = display_text.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from src.ingest.chunking.models import (
    ChildChunk,
    ChunkingConfig,
    ChunkingResult,
    ParentChunk,
)
from src.ingest.chunking.recursive_splitter import RecursiveTokenSplitter
from src.ingest.chunking.tokenizer import estimate_tokens
from src.ingest.parsers.structured_doc import Block, StructuredDoc
from src.interfaces import IChunker


class SimpleChunker(IChunker):
    """Reading-order fixed-size packer. Ignores headings as structure."""

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig(use_heading_fusion=False)
        self.splitter = RecursiveTokenSplitter(
            target_tokens=self.config.child_target_tokens,
            max_tokens=self.config.child_max_tokens,
            min_tokens=self.config.child_min_tokens,
            overlap_ratio=self.config.child_overlap,
        )

    def chunk(
        self, structured_doc: StructuredDoc, config: ChunkingConfig | None = None
    ) -> ChunkingResult:
        """Pack document blocks into fixed-size windows without heading fusion."""
        cfg = config or self.config
        doc_id = structured_doc.doc_id
        breadcrumb = structured_doc.title or "Document"

        blocks = [b for b in structured_doc.blocks if b.text.strip()]
        if not blocks:
            return ChunkingResult(
                doc_id=doc_id, parents=[], children=[], chunking_version="simple-v1"
            )

        windows = self._pack_windows(blocks, cfg)
        parents: list[ParentChunk] = []
        children: list[ChildChunk] = []

        for idx, window_blocks in enumerate(windows):
            text = "\n\n".join(b.text.strip() for b in window_blocks)
            page = self._majority_page(window_blocks)
            parent_id = self._id(f"{doc_id}:p:{idx}", prefix="p")
            parent = ParentChunk(
                parent_id=parent_id,
                doc_id=doc_id,
                breadcrumb=breadcrumb,
                text=text,
                token_count=estimate_tokens(text),
                page_start=min(b.page for b in window_blocks),
                page_end=max(b.page for b in window_blocks),
            )
            parents.append(parent)

            pieces = self.splitter.split_text(text) or [text]
            for piece in pieces:
                children.append(
                    self._make_child(
                        doc_id=doc_id,
                        parent_id=parent_id,
                        breadcrumb=breadcrumb,
                        text=piece,
                        page=page,
                        index=len(children),
                    )
                )

        for i, child in enumerate(children):
            if i > 0:
                child.prev_chunk_id = children[i - 1].chunk_id
            if i < len(children) - 1:
                child.next_chunk_id = children[i + 1].chunk_id

        return ChunkingResult(
            doc_id=doc_id,
            parents=parents,
            children=children,
            chunking_version="simple-v1",
        )

    def _pack_windows(self, blocks: list[Block], cfg: ChunkingConfig) -> list[list[Block]]:
        """Greedy pack blocks into windows targeting child_target_tokens."""
        windows: list[list[Block]] = []
        current: list[Block] = []
        current_tokens = 0

        for block in blocks:
            b_tokens = estimate_tokens(block.text)
            would_exceed = current and (
                current_tokens + b_tokens > cfg.child_max_tokens
                or current_tokens >= cfg.child_target_tokens
            )
            if would_exceed:
                windows.append(current)
                current = [block]
                current_tokens = b_tokens
            else:
                current.append(block)
                current_tokens += b_tokens

        if current:
            windows.append(current)
        return windows

    def _make_child(
        self,
        doc_id: str,
        parent_id: str,
        breadcrumb: str,
        text: str,
        page: int,
        index: int,
    ) -> ChildChunk:
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        chunk_id = self._id(f"{doc_id}:{parent_id}:{index}:{content_hash}", prefix="c")
        return ChildChunk(
            chunk_id=chunk_id,
            doc_id=doc_id,
            parent_id=parent_id,
            breadcrumb=breadcrumb,
            display_text=text,
            embedding_text=text,
            child_tokens=estimate_tokens(text),
            chunk_index=index,
            chunk_type="text",
            page=page,
            bbox=None,
            content_hash=content_hash,
        )

    @staticmethod
    def _majority_page(blocks: list[Block]) -> int:
        weights: dict[int, int] = defaultdict(int)
        for block in blocks:
            weights[block.page] += estimate_tokens(block.text)
        return max(weights, key=weights.get)

    @staticmethod
    def _id(raw: str, prefix: str) -> str:
        return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"
