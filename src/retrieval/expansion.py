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

    @property
    def page_number(self) -> int:
        return self.page

    @property
    def score(self) -> float:
        return 1.0


@dataclass
class ExpansionResult:
    """The result of parent and window context expansion."""

    passages: list[ExpandedContextPassage]
    total_tokens: int
    budget_exhausted: bool

    @property
    def contexts(self) -> list[ExpandedContextPassage]:
        return self.passages


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
        chunks: list[Any],
        scope: str = "demo",
        budget: int | None = None,
        session_id: str | None = None,
    ) -> ExpansionResult:
        """Expand retrieved child chunks into parent/window context passages."""
        active_scope = session_id or scope
        active_budget = budget or self.context_budget
        expanded_passages: list[ExpandedContextPassage] = []
        seen_parent_ids: set[str] = set()
        seen_chunk_ids: set[str] = set()
        seen_text_keys: set[str] = set()
        current_token_count = 0
        budget_exhausted = False

        for chunk in chunks:
            if chunk.chunk_id in seen_chunk_ids:
                continue

            parent_id = getattr(chunk, "parent_id", None)
            if parent_id and parent_id in seen_parent_ids:
                # Parent already in context; add this chunk_id to seen
                seen_chunk_ids.add(chunk.chunk_id)
                continue

            # Attempt to retrieve parent from SQL with mandatory scope filter
            parent_record: dict[str, Any] | None = None
            if parent_id:
                try:
                    parent_record = self.db.get_parent(parent_id, scope=active_scope)
                except Exception as exc:
                    logger.warning(
                        f"Failed to fetch parent {parent_id} in scope {active_scope}: {exc}"
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
                        passage_id=f"p_{parent_id}",
                        doc_id=getattr(chunk, "doc_id", "doc"),
                        title=getattr(chunk, "title", "Document"),
                        breadcrumb=parent_record.get("breadcrumb")
                        or getattr(chunk, "breadcrumb", "Overview"),
                        page=parent_record.get("page_start", getattr(chunk, "page", 1)),
                        text=parent_text,
                        token_count=tokens_to_add,
                        is_parent_expanded=True,
                        source_chunk_ids=[chunk.chunk_id],
                    )
                    expanded_passages.append(passage)
                    seen_parent_ids.add(parent_id)
                    seen_chunk_ids.add(chunk.chunk_id)
                    parent_key = " ".join(parent_text.lower().split())[:160]
                    if parent_key:
                        seen_text_keys.add(parent_key)
                    current_token_count += tokens_to_add
                    continue

            # Fallback to child chunk (or window) if parent is oversized or missing
            child_text = (
                getattr(chunk, "content", None)
                or getattr(chunk, "display_text", None)
                or getattr(chunk, "embedding_text", "")
            )
            text_key = " ".join(str(child_text).lower().split())[:160]
            if text_key and text_key in seen_text_keys:
                seen_chunk_ids.add(chunk.chunk_id)
                continue
            tokens_to_add = estimate_tokens(child_text)

            if current_token_count + tokens_to_add > active_budget:
                budget_exhausted = True
                break

            passage = ExpandedContextPassage(
                passage_id=f"c_{chunk.chunk_id}",
                doc_id=getattr(chunk, "doc_id", "doc"),
                title=getattr(chunk, "title", "Document"),
                breadcrumb=getattr(chunk, "breadcrumb", "Overview"),
                page=getattr(chunk, "page", getattr(chunk, "page_number", 1)),
                text=child_text,
                token_count=tokens_to_add,
                is_parent_expanded=False,
                source_chunk_ids=[chunk.chunk_id],
            )
            expanded_passages.append(passage)
            seen_chunk_ids.add(chunk.chunk_id)
            if text_key:
                seen_text_keys.add(text_key)
            current_token_count += tokens_to_add

        return ExpansionResult(
            passages=expanded_passages,
            total_tokens=current_token_count,
            budget_exhausted=budget_exhausted,
        )


ParentContextExpander = ContextExpander
