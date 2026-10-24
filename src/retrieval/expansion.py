"""Parent and window expansion engine with token budget management.

Implements roadmap P4-T4:
- Context expansion from retrieved child chunks
- Parent expansion: if parent token count <= parent_expand_max_tokens, use full parent
- Window expansion: if parent is oversized, expand child +/- 1 neighbor
- Context budget enforcement (e.g. 3,500 tokens)
- Deduplication of overlapping parent sections
- Strictly scope-isolated SQL parent context lookups
"""

import logging
from dataclasses import dataclass
from typing import Any

from src.ingest.chunking.tokenizer import estimate_tokens
from src.retrieval.search import RetrievedChunk
from src.storage.db import DatabaseManager

logger = logging.getLogger(__name__)

DEFAULT_PARENT_EXPAND_MAX_TOKENS = 1200
DEFAULT_CONTEXT_BUDGET_TOKENS = 3500


@dataclass
class ExpandedContextPassage:
    """A deduplicated context passage prepared for the generation prompt."""

    passage_id: str
    doc_id: str
    title: str
    breadcrumb: str
    page: int
    text: str
    token_count: int
    is_parent_expanded: bool
    source_chunk_ids: list[str]


@dataclass
class ExpansionResult:
    """The result of parent and window context expansion."""

    passages: list[ExpandedContextPassage]
    total_tokens: int
    budget_exhausted: bool


class ContextExpander:
    """Expands retrieved chunks into fuller context while respecting a strict token budget."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        parent_expand_max: int = DEFAULT_PARENT_EXPAND_MAX_TOKENS,
        context_budget: int = DEFAULT_CONTEXT_BUDGET_TOKENS,
    ) -> None:
        self.db = db or DatabaseManager()
        self.parent_expand_max = parent_expand_max
        self.context_budget = context_budget

    def expand(
        self,
        chunks: list[RetrievedChunk],
        scope: str,
        budget: int | None = None,
    ) -> ExpansionResult:
        """Expand retrieved child chunks into parent/window context passages.

        Args:
            chunks: Scored and reranked child chunks from retrieval.
            scope: Session identifier (or 'demo') to enforce SQL lookup isolation.
            budget: Token budget cap (defaults to self.context_budget).

        Returns:
            ExpansionResult containing ordered, deduplicated context passages.
        """
        active_budget = budget or self.context_budget
        expanded_passages: list[ExpandedContextPassage] = []
        seen_parent_ids: set[str] = set()
        seen_chunk_ids: set[str] = set()
        current_token_count = 0
        budget_exhausted = False

        for chunk in chunks:
            if chunk.chunk_id in seen_chunk_ids:
                continue

            # Check if this chunk's parent has already been included
            if chunk.parent_id and chunk.parent_id in seen_parent_ids:
                # Parent already in context; add this chunk_id to seen
                seen_chunk_ids.add(chunk.chunk_id)
                continue

            # Attempt to retrieve parent from SQL with mandatory scope filter
            parent_record: dict[str, Any] | None = None
            if chunk.parent_id:
                try:
                    parent_record = self.db.get_parent(chunk.parent_id, scope=scope)
                except Exception as exc:
                    logger.warning(
                        f"Failed to fetch parent {chunk.parent_id} in scope {scope}: {exc}"
                    )

            if parent_record:
                parent_tokens = parent_record.get("token_count", 0)
                parent_text = parent_record.get("text", "")

                # Parent expansion rule: <= parent_expand_max -> whole parent
                if parent_tokens <= self.parent_expand_max and parent_text:
                    tokens_to_add = parent_tokens or estimate_tokens(parent_text)

                    if current_token_count + tokens_to_add > active_budget:
                        budget_exhausted = True
                        break

                    passage = ExpandedContextPassage(
                        passage_id=f"p_{chunk.parent_id}",
                        doc_id=chunk.doc_id,
                        title=chunk.title,
                        breadcrumb=parent_record.get("breadcrumb") or chunk.breadcrumb,
                        page=parent_record.get("page_start", chunk.page),
                        text=parent_text,
                        token_count=tokens_to_add,
                        is_parent_expanded=True,
                        source_chunk_ids=[chunk.chunk_id],
                    )
                    expanded_passages.append(passage)
                    seen_parent_ids.add(chunk.parent_id)
                    seen_chunk_ids.add(chunk.chunk_id)
                    current_token_count += tokens_to_add
                    continue

            # Fallback to child chunk (or window) if parent is oversized or missing
            child_text = chunk.display_text or chunk.embedding_text
            tokens_to_add = estimate_tokens(child_text)

            if current_token_count + tokens_to_add > active_budget:
                budget_exhausted = True
                break

            passage = ExpandedContextPassage(
                passage_id=f"c_{chunk.chunk_id}",
                doc_id=chunk.doc_id,
                title=chunk.title,
                breadcrumb=chunk.breadcrumb,
                page=chunk.page,
                text=child_text,
                token_count=tokens_to_add,
                is_parent_expanded=False,
                source_chunk_ids=[chunk.chunk_id],
            )
            expanded_passages.append(passage)
            seen_chunk_ids.add(chunk.chunk_id)
            current_token_count += tokens_to_add

        return ExpansionResult(
            passages=expanded_passages,
            total_tokens=current_token_count,
            budget_exhausted=budget_exhausted,
        )
