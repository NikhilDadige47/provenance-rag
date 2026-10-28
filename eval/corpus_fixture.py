"""Compact Apple 10-K passages covering every golden-set answerable query.

CI cannot ingest the full PDFs on every run. This fixture places the ground-truth
figures on the pages recorded in eval/golden_set.jsonl so offline retrieval
ablations stay aligned with the published answer key.
"""

from __future__ import annotations

from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc

YEAR_DOCS: dict[int, dict[str, object]] = {
    2023: {
        "filename": "Apple-Annual-Report-2023.pdf",
        "title": "Apple Inc. Form 10-K Fiscal Year 2023",
        "products_page": 28,
        "income_page": 34,
        "balance_page": 36,
        "segment_page": 27,
        "net_sales": "383,285",
        "operating_income": "114,301",
        "rd": "29,915",
        "net_income": "96,995",
        "diluted_eps": "6.13",
        "iphone": "200,583",
        "services": "85,200",
        "mac": "29,357",
        "wearables": "39,845",
        "americas": "162,560",
        "europe": "94,294",
        "greater_china": "72,559",
        "assets": "352,583",
        "cash": "29,965",
        "equity": "62,146",
        "gross_margin": "169,148",
        "cost_of_sales": "214,137",
        "tax_provision": "16,741",
        "income_before_tax": "113,736",
    },
    2024: {
        "filename": "Apple-Annual-Report-2024.pdf",
        "title": "Apple Inc. Form 10-K Fiscal Year 2024",
        "products_page": 28,
        "income_page": 35,
        "balance_page": 37,
        "segment_page": 27,
        "net_sales": "391,035",
        "operating_income": "123,216",
        "rd": "31,370",
        "net_income": "93,736",
        "diluted_eps": "6.08",
        "iphone": "201,183",
        "services": "96,169",
        "mac": "29,984",
        "wearables": "37,005",
        "americas": "167,045",
        "europe": "101,328",
        "greater_china": "66,952",
        "assets": "364,980",
        "cash": "29,943",
        "equity": "56,950",
        "gross_margin": "180,683",
        "cost_of_sales": "210,352",
        "tax_provision": "29,749",
        "income_before_tax": "123,485",
    },
    2025: {
        "filename": "Apple-Annual-Report-2025.pdf",
        "title": "Apple Inc. Form 10-K Fiscal Year 2025",
        "products_page": 28,
        "income_page": 35,
        "balance_page": 37,
        "segment_page": 27,
        "net_sales": "416,161",
        "operating_income": "133,050",
        "rd": "34,550",
        "net_income": "112,010",
        "diluted_eps": "7.46",
        "iphone": "209,586",
        "services": "109,158",
        "mac": "33,708",
        "wearables": "35,688",
        "americas": "178,353",
        "europe": "111,032",
        "greater_china": "64,377",
        "assets": "359,241",
        "cash": "35,934",
        "equity": "73,733",
        "gross_margin": "195,201",
        "cost_of_sales": "220,960",
        "tax_provision": "20,719",
        "income_before_tax": "132,729",
    },
}


def _filler(year: int, topic: str, n_sentences: int = 14) -> str:
    """Year-tagged boilerplate so simple windows fill before the financial tables."""
    sentences = [
        (
            f"During fiscal {year} the company continued {topic} across hardware, "
            "services, and regional operations without restating Item 8 figures here."
        )
        for _ in range(n_sentences)
    ]
    return " ".join(sentences)


def _block(
    text: str,
    page: int,
    order: int,
    block_type: BlockType = BlockType.PARAGRAPH,
    level: int | None = None,
) -> Block:
    return Block(type=block_type, text=text, level=level, page=page, order=order)


def _year_document(year: int) -> StructuredDoc:
    facts = YEAR_DOCS[year]
    filename = str(facts["filename"])
    title = str(facts["title"])
    products_page = int(facts["products_page"])
    income_page = int(facts["income_page"])
    balance_page = int(facts["balance_page"])
    segment_page = int(facts["segment_page"])
    order = 0
    blocks: list[Block] = []

    def add(
        text: str,
        page: int,
        block_type: BlockType = BlockType.PARAGRAPH,
        level: int | None = None,
    ) -> None:
        nonlocal order
        blocks.append(_block(text, page, order, block_type, level))
        order += 1

    add("Item 1. Business", 1, BlockType.HEADING, 1)
    add(_filler(year, "product design and retail expansion"), 1)

    add("Item 1A. Risk Factors", 2, BlockType.HEADING, 1)
    add(_filler(year, "supply chain and regulatory risk disclosure", n_sentences=16), 2)
    add(
        "Net sales increased year over year as described in Item 8. Exact amounts appear "
        "only in the consolidated statements of operations.",
        2,
    )

    add("Item 8. Financial Statements and Supplementary Data", segment_page, BlockType.HEADING, 1)
    add(f"Fiscal Year {year}", segment_page, BlockType.HEADING, 2)
    add("Net sales by reportable segment", segment_page, BlockType.HEADING, 3)
    add(
        (
            "| Segment | Net Sales (millions) |\n|---|---|\n"
            f"| Americas | ${facts['americas']} |\n"
            f"| Europe | ${facts['europe']} |\n"
            f"| Greater China | ${facts['greater_china']} |"
        ),
        segment_page,
        BlockType.TABLE,
    )
    add(
        (
            f"Europe net sales were ${facts['europe']} million and Greater China net sales "
            f"were ${facts['greater_china']} million. Americas net sales were "
            f"${facts['americas']} million."
        ),
        segment_page,
    )
    if year == 2025:
        add(
            "New U.S. Tariffs were announced beginning in the second quarter of 2025 on "
            "imports from China, India, Japan, South Korea, Taiwan, Vietnam and the EU.",
            segment_page,
        )

    add(f"Fiscal Year {year} net sales by category", products_page, BlockType.HEADING, 2)
    add("Products and services category table", products_page, BlockType.HEADING, 3)
    add(
        (
            "| Category | Net Sales (millions) |\n|---|---|\n"
            f"| iPhone | ${facts['iphone']} |\n"
            f"| Mac | ${facts['mac']} |\n"
            f"| Wearables, Home and Accessories | ${facts['wearables']} |\n"
            f"| Services | ${facts['services']} |"
        ),
        products_page,
        BlockType.TABLE,
    )
    add(
        (
            f"iPhone net sales were ${facts['iphone']} million. Services net sales were "
            f"${facts['services']} million. Mac net sales were ${facts['mac']} million. "
            f"Wearables, Home and Accessories net sales were ${facts['wearables']} million."
        ),
        products_page,
    )

    add("Consolidated Statements of Operations", income_page, BlockType.HEADING, 2)
    add(
        (
            "| Line item | Amount (millions) |\n|---|---|\n"
            f"| Net sales | ${facts['net_sales']} |\n"
            f"| Total cost of sales | ${facts['cost_of_sales']} |\n"
            f"| Gross margin | ${facts['gross_margin']} |\n"
            f"| Research and development | ${facts['rd']} |\n"
            f"| Operating income | ${facts['operating_income']} |\n"
            f"| Income before taxes | ${facts['income_before_tax']} |\n"
            f"| Provision for income taxes | ${facts['tax_provision']} |\n"
            f"| Net income | ${facts['net_income']} |\n"
            f"| Diluted earnings per share | ${facts['diluted_eps']} |"
        ),
        income_page,
        BlockType.TABLE,
    )
    add(
        (
            f"Total net sales were ${facts['net_sales']} million. Operating income was "
            f"${facts['operating_income']} million. Research and development expense was "
            f"${facts['rd']} million. Net income was ${facts['net_income']} million. "
            f"Diluted earnings per share were ${facts['diluted_eps']}. Gross margin was "
            f"${facts['gross_margin']} million with total cost of sales of "
            f"${facts['cost_of_sales']} million. Provision for income taxes was "
            f"${facts['tax_provision']} million on income before taxes of "
            f"${facts['income_before_tax']} million."
        ),
        income_page,
    )

    add("Consolidated Balance Sheets", balance_page, BlockType.HEADING, 2)
    add(
        (
            "| Line item | Amount (millions) |\n|---|---|\n"
            f"| Cash and cash equivalents | ${facts['cash']} |\n"
            f"| Total assets | ${facts['assets']} |\n"
            f"| Total shareholders' equity | ${facts['equity']} |"
        ),
        balance_page,
        BlockType.TABLE,
    )
    add(
        (
            f"Total assets were ${facts['assets']} million and cash and cash equivalents "
            f"were ${facts['cash']} million. Total shareholders' equity was "
            f"${facts['equity']} million."
        ),
        balance_page,
    )

    return StructuredDoc(
        doc_id=filename,
        title=title,
        page_count=max(balance_page, income_page, products_page, segment_page),
        parser_used="eval_fixture",
        parser_version="golden-v1",
        blocks=blocks,
    )


def build_apple_corpus() -> list[StructuredDoc]:
    """Return one structured document per fiscal year in the golden set."""
    return [_year_document(year) for year in (2023, 2024, 2025)]
