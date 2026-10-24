"""Markdown table splitting with header preservation.

Ensures small tables remain whole, while oversized tables are split
by rows with the table header repeated across every split piece.
"""

from src.ingest.chunking.tokenizer import estimate_tokens


def split_markdown_table(table_text: str, max_tokens: int = 800) -> list[str]:
    """Split an oversized Markdown table into chunks while repeating header rows.

    Never splits across a single table row.
    """
    lines = [line.strip() for line in table_text.strip().splitlines() if line.strip()]
    if not lines:
        return []

    # If the entire table fits comfortably, return it as a single piece
    if estimate_tokens(table_text) <= max_tokens or len(lines) <= 2:
        return [table_text]

    # Detect header row and separator line (e.g., | col1 | col2 | and |--|--|)
    header_lines: list[str] = []
    data_lines: list[str] = []

    if len(lines) >= 2 and "|" in lines[0] and ("-" in lines[1] or "|" in lines[1]):
        header_lines = [lines[0], lines[1]]
        data_lines = lines[2:]
    else:
        # Fallback if no clear separator line exists
        header_lines = [lines[0]]
        data_lines = lines[1:]

    header_block = "\n".join(header_lines)
    header_tokens = estimate_tokens(header_block)

    # If even the header exceeds max_tokens, return whole lines
    if header_tokens >= max_tokens:
        return [table_text]

    chunks: list[str] = []
    current_rows: list[str] = []
    current_tokens = header_tokens

    for row in data_lines:
        row_tokens = estimate_tokens(row)

        if current_rows and (current_tokens + row_tokens > max_tokens):
            # Finalize current chunk with repeated headers
            chunk_content = header_block + "\n" + "\n".join(current_rows)
            chunks.append(chunk_content)
            current_rows = [row]
            current_tokens = header_tokens + row_tokens
        else:
            current_rows.append(row)
            current_tokens += row_tokens

    if current_rows:
        chunk_content = header_block + "\n" + "\n".join(current_rows)
        chunks.append(chunk_content)

    return chunks
