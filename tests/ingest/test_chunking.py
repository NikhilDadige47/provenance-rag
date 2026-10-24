"""Unit tests for the hybrid chunking subsystem."""

from src.ingest.chunking.heading_stack import HeadingStack, tag_blocks_with_breadcrumbs
from src.ingest.chunking.hybrid_chunker import HybridChunker
from src.ingest.chunking.recursive_splitter import RecursiveTokenSplitter
from src.ingest.chunking.table_splitter import split_markdown_table
from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc


def test_heading_stack_hierarchy():
    """Verify heading stack correctly pushes and clears deeper levels."""
    stack = HeadingStack(doc_title="Annual Report")
    assert stack.current_breadcrumb() == "Annual Report"

    stack.push(1, "Financial Highlights")
    assert stack.current_breadcrumb() == "Annual Report > Financial Highlights"

    stack.push(2, "Revenue Breakdown")
    assert stack.current_breadcrumb() == "Annual Report > Financial Highlights > Revenue Breakdown"

    # Higher level heading should clear level 2
    stack.push(1, "Governance")
    assert stack.current_breadcrumb() == "Annual Report > Governance"


def test_tag_blocks_with_breadcrumbs():
    """Verify blocks receive hierarchical breadcrumbs."""
    blocks = [
        Block(type=BlockType.HEADING, text="Overview", level=1, page=1, order=0),
        Block(type=BlockType.PARAGRAPH, text="Company intro text.", page=1, order=1),
        Block(type=BlockType.HEADING, text="Details", level=2, page=1, order=2),
        Block(type=BlockType.PARAGRAPH, text="Detailed metrics.", page=1, order=3),
    ]

    tagged = tag_blocks_with_breadcrumbs(blocks, doc_title="Doc1")
    assert len(tagged) == 4
    assert tagged[1][1] == "Doc1 > Overview"
    assert tagged[3][1] == "Doc1 > Overview > Details"


def test_split_markdown_table():
    """Verify small tables stay whole while large tables repeat header rows."""
    small_table = "| Col A | Col B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    assert split_markdown_table(small_table, max_tokens=500) == [small_table]

    # Create a larger table with multiple rows
    rows = [f"| Item {i} | Value {i} |" for i in range(20)]
    large_table = "| Name | Value |\n|---|---|\n" + "\n".join(rows)

    pieces = split_markdown_table(large_table, max_tokens=50)
    assert len(pieces) > 1
    for piece in pieces:
        # Every piece MUST contain the header
        assert "| Name | Value |" in piece
        assert "|---|---|" in piece


def test_recursive_splitter():
    """Verify text is split along natural boundaries with overlap."""
    splitter = RecursiveTokenSplitter(target_tokens=30, max_tokens=50, min_tokens=10, overlap_ratio=0.2)
    sample_text = (
        "Alpha beta gamma delta. " * 10
        + "\n\n"
        + "Epsilon zeta eta theta. " * 10
    )

    chunks = splitter.split_text(sample_text)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.strip()) > 0


def test_hybrid_chunker_end_to_end():
    """Verify end-to-end chunking produces valid parents, children, and heading fusion."""
    doc = StructuredDoc(
        doc_id="doc_test_123",
        title="Acme Q3 Report",
        page_count=2,
        parser_used="test_parser",
        blocks=[
            Block(type=BlockType.HEADING, text="Executive Summary", level=1, page=1, order=0),
            Block(type=BlockType.PARAGRAPH, text="Q3 revenue grew by 15% year-over-year.", page=1, order=1),
            Block(type=BlockType.TABLE, text="| Metric | Q3 |\n|---|---|\n| Revenue | $15M |", page=1, order=2),
            Block(type=BlockType.HEADING, text="Risk Factors", level=1, page=2, order=3),
            Block(type=BlockType.PARAGRAPH, text="Supply chain constraints in APAC.", page=2, order=4),
        ],
    )

    chunker = HybridChunker()
    result = chunker.chunk(doc)

    assert result.doc_id == "doc_test_123"
    assert len(result.parents) >= 2
    assert len(result.children) >= 3

    # Heading fusion verification
    first_child = result.children[0]
    assert "Acme Q3 Report > Executive Summary" in first_child.breadcrumb
    assert f"[{first_child.breadcrumb}]" in first_child.embedding_text
    assert first_child.display_text == "Q3 revenue grew by 15% year-over-year."
    assert first_child.display_text not in first_child.breadcrumb

    # Linking verification
    assert first_child.prev_chunk_id is None
    assert first_child.next_chunk_id == result.children[1].chunk_id
    assert result.children[1].prev_chunk_id == first_child.chunk_id

    # Determinism verification: chunking the same doc yields identical IDs
    result_second = chunker.chunk(doc)
    assert [c.chunk_id for c in result.children] == [c.chunk_id for c in result_second.children]
    assert [p.parent_id for p in result.parents] == [p.parent_id for p in result_second.parents]


def test_hybrid_chunker_empty_doc():
    """Verify empty StructuredDoc produces empty result gracefully."""
    doc = StructuredDoc(
        doc_id="empty_doc",
        title="Empty",
        page_count=1,
        parser_used="none",
        blocks=[],
    )
    chunker = HybridChunker()
    result = chunker.chunk(doc)
    assert len(result.parents) == 0
    assert len(result.children) == 0
