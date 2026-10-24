"""Structure pass and heading stack tracking.

Maintains a hierarchical heading stack to generate contextual breadcrumb trails
for each block and section in the document according to architecture spec §4.4.2.
"""

from src.ingest.chunking.tokenizer import estimate_tokens, truncate_to_tokens
from src.ingest.parsers.structured_doc import Block, BlockType


class HeadingStack:
    """Manages active headings during a sequential document walk."""

    def __init__(self, doc_title: str = "Document", prefix_max_tokens: int = 60) -> None:
        self.doc_title = doc_title.strip() or "Document"
        self.prefix_max_tokens = prefix_max_tokens
        # Mapping from heading level (1..6) to heading title
        self._stack: dict[int, str] = {}

    def push(self, level: int, title: str) -> None:
        """Register a new heading at the given level and clear any deeper levels."""
        clean_title = title.strip()
        if not clean_title:
            return

        # Ensure valid heading level
        lvl = max(1, min(6, level))

        # Set this level
        self._stack[lvl] = clean_title

        # Clear any deeper heading levels
        for deeper in range(lvl + 1, 7):
            self._stack.pop(deeper, None)

    def current_breadcrumb(self) -> str:
        """Return the current hierarchical breadcrumb string.

        Format: DocTitle > H1 > H2 > H3...
        Capped to prefix_max_tokens.
        """
        parts = [self.doc_title]
        # Traverse levels in ascending order 1..6
        for lvl in range(1, 7):
            if lvl in self._stack:
                parts.append(self._stack[lvl])

        breadcrumb = " > ".join(parts)
        if estimate_tokens(breadcrumb) > self.prefix_max_tokens:
            breadcrumb = truncate_to_tokens(breadcrumb, self.prefix_max_tokens)

        return breadcrumb

    def current_lowest_heading(self) -> str:
        """Return the most specific active heading text or doc title."""
        for lvl in range(6, 0, -1):
            if lvl in self._stack:
                return self._stack[lvl]
        return self.doc_title


def tag_blocks_with_breadcrumbs(
    blocks: list[Block], doc_title: str, prefix_max_tokens: int = 60
) -> list[tuple[Block, str]]:
    """Walk blocks in reading order, maintaining heading stack and tagging each block.

    Returns list of (Block, breadcrumb) tuples.
    """
    stack = HeadingStack(doc_title=doc_title, prefix_max_tokens=prefix_max_tokens)
    tagged_blocks: list[tuple[Block, str]] = []

    for block in blocks:
        if block.type == BlockType.HEADING:
            level = block.level if block.level is not None else 2
            stack.push(level, block.text)
            # Headings also carry their own hierarchy breadcrumb
            tagged_blocks.append((block, stack.current_breadcrumb()))
        else:
            tagged_blocks.append((block, stack.current_breadcrumb()))

    return tagged_blocks
