"""LlamaParse adapter and markdown normalizer.

Interacts with LlamaIndex Cloud's parsing API using visitor-supplied keys,
enforcing secure egress and normalizing Markdown layouts into StructuredDoc.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

import httpx

from src.ingest.parsers.cleanup import clean_blocks
from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc
from src.interfaces import IParser
from src.security.egress import create_secure_client
from src.security.errors import (
    InvalidKeyError,
    KeySecurityError,
    ProviderTimeoutError,
    RateLimitedError,
)
from src.security.secret import Secret

LLAMAPARSE_UPLOAD_URL = "https://api.cloud.llamaindex.ai/api/v1/parsing/upload"
LLAMAPARSE_JOB_URL = "https://api.cloud.llamaindex.ai/api/v1/parsing/job"


class LlamaParseNormalizer:
    """Normalizes raw Markdown output from LlamaParse into StructuredDoc blocks."""

    PAGE_MARKER_RE = re.compile(
        r"(?:---\s*\[Page\s*(\d+)\]\s*---|<!--\s*page\s*(\d+)\s*-->|\f)", re.IGNORECASE
    )
    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
    TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")

    @classmethod
    def parse_markdown_to_blocks(cls, markdown: str) -> list[Block]:
        """Convert markdown text into a sequence of typed blocks."""
        if not markdown or not markdown.strip():
            return []

        blocks: list[Block] = []
        current_page = 1

        lines = markdown.splitlines()
        idx = 0
        total_lines = len(lines)

        while idx < total_lines:
            line = lines[idx]
            stripped = line.strip()

            # 1. Check for page markers
            page_match = cls.PAGE_MARKER_RE.search(stripped)
            if page_match:
                page_str = page_match.group(1) or page_match.group(2)
                if page_str:
                    current_page = int(page_str)
                else:
                    current_page += 1
                idx += 1
                continue

            if not stripped:
                idx += 1
                continue

            # 2. Check for Headings
            heading_match = cls.HEADING_RE.match(stripped)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                if text:
                    blocks.append(
                        Block(
                            type=BlockType.HEADING,
                            text=text,
                            level=level,
                            page=current_page,
                            order=len(blocks),
                        )
                    )
                idx += 1
                continue

            # 3. Check for Code Blocks
            if stripped.startswith("```"):
                code_lines = [line]
                idx += 1
                while idx < total_lines and not lines[idx].strip().startswith("```"):
                    code_lines.append(lines[idx])
                    idx += 1
                if idx < total_lines:
                    code_lines.append(lines[idx])
                    idx += 1
                code_text = "\n".join(code_lines).strip()
                if code_text:
                    blocks.append(
                        Block(
                            type=BlockType.CODE,
                            text=code_text,
                            page=current_page,
                            order=len(blocks),
                        )
                    )
                continue

            # 4. Check for Tables
            if cls.TABLE_ROW_RE.match(stripped):
                table_lines = [line]
                idx += 1
                while idx < total_lines and cls.TABLE_ROW_RE.match(lines[idx].strip()):
                    table_lines.append(lines[idx])
                    idx += 1
                table_text = "\n".join(table_lines).strip()
                if table_text:
                    blocks.append(
                        Block(
                            type=BlockType.TABLE,
                            text=table_text,
                            page=current_page,
                            order=len(blocks),
                        )
                    )
                continue

            # 5. Check for List Items
            if stripped.startswith(("- ", "* ", "+ ", "• ")) or re.match(r"^\d+\.\s+", stripped):
                list_lines = [stripped]
                idx += 1
                while idx < total_lines:
                    next_stripped = lines[idx].strip()
                    if next_stripped.startswith(("- ", "* ", "+ ", "• ")) or re.match(
                        r"^\d+\.\s+", next_stripped
                    ):
                        break
                    if (
                        not next_stripped
                        or cls.HEADING_RE.match(next_stripped)
                        or cls.TABLE_ROW_RE.match(next_stripped)
                    ):
                        break
                    list_lines.append(next_stripped)
                    idx += 1
                blocks.append(
                    Block(
                        type=BlockType.LIST_ITEM,
                        text=" ".join(list_lines),
                        page=current_page,
                        order=len(blocks),
                    )
                )
                continue

            # 6. Paragraph (accumulate consecutive text lines)
            para_lines = [stripped]
            idx += 1
            while idx < total_lines:
                next_line = lines[idx].strip()
                if (
                    not next_line
                    or cls.PAGE_MARKER_RE.search(next_line)
                    or cls.HEADING_RE.match(next_line)
                    or cls.TABLE_ROW_RE.match(next_line)
                    or next_line.startswith("```")
                    or next_line.startswith(("- ", "* ", "+ ", "• "))
                    or re.match(r"^\d+\.\s+", next_line)
                ):
                    break
                para_lines.append(next_line)
                idx += 1

            para_text = " ".join(para_lines).strip()
            if para_text:
                blocks.append(
                    Block(
                        type=BlockType.PARAGRAPH,
                        text=para_text,
                        page=current_page,
                        order=len(blocks),
                    )
                )

        return blocks


class LlamaParseAdapter(IParser):
    """Adapter for LlamaIndex Cloud's LlamaParse service."""

    @property
    def name(self) -> str:
        return "llamaparse"

    @property
    def requires_key(self) -> bool:
        return True

    async def parse(self, file_path: Path, api_key: Secret | None = None) -> StructuredDoc:
        """Submit PDF to LlamaParse API, poll for completion, and return StructuredDoc."""
        if not api_key or not api_key.reveal():
            raise KeySecurityError("LlamaParse requires an API key, but none was provided.")

        headers = {"Authorization": f"Bearer {api_key.reveal()}"}

        async with create_secure_client() as client:
            try:
                # 1. Upload file
                with open(file_path, "rb") as f:
                    files = {"file": (file_path.name, f, "application/pdf")}
                    data = {"language": "en"}
                    upload_resp = await client.post(
                        LLAMAPARSE_UPLOAD_URL,
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=30.0,
                    )

                if upload_resp.status_code in {401, 403}:
                    raise InvalidKeyError(provider=self.name, is_visitor_key=True)
                if upload_resp.status_code == 429:
                    raise RateLimitedError(provider=self.name, is_visitor_key=True)
                upload_resp.raise_for_status()

                job_id = upload_resp.json().get("id")
                if not job_id:
                    raise RuntimeError("LlamaParse did not return a job ID.")

                # 2. Poll for job completion
                poll_url = f"{LLAMAPARSE_JOB_URL}/{job_id}"
                max_polls = 60
                markdown_result: str | None = None

                for _ in range(max_polls):
                    await asyncio.sleep(2.0)
                    job_resp = await client.get(poll_url, headers=headers, timeout=10.0)

                    if job_resp.status_code in {401, 403}:
                        raise InvalidKeyError(provider=self.name, is_visitor_key=True)
                    job_resp.raise_for_status()

                    job_data = job_resp.json()
                    status = job_data.get("status")

                    if status == "SUCCESS":
                        # Fetch result markdown
                        result_url = f"{LLAMAPARSE_JOB_URL}/{job_id}/result/markdown"
                        res_resp = await client.get(result_url, headers=headers, timeout=15.0)
                        res_resp.raise_for_status()
                        markdown_result = res_resp.json().get("markdown", "")
                        break
                    elif status in {"ERROR", "FAILED"}:
                        error_msg = job_data.get("error", "Unknown LlamaParse error")
                        raise RuntimeError(f"LlamaParse job failed: {error_msg}")

                if markdown_result is None:
                    raise ProviderTimeoutError(provider=self.name)

            except httpx.TimeoutException:
                raise ProviderTimeoutError(provider=self.name) from None

        # 3. Normalize into StructuredDoc
        blocks = LlamaParseNormalizer.parse_markdown_to_blocks(markdown_result)
        total_pages = max([b.page for b in blocks], default=1)
        cleaned = clean_blocks(blocks, total_pages=total_pages)

        return StructuredDoc(
            doc_id=f"doc_{uuid.uuid4().hex[:12]}",
            title=file_path.stem.replace("_", " ").title(),
            page_count=total_pages,
            parser_used=self.name,
            parser_version="llamaparse-v1",
            blocks=cleaned,
            raw_text=markdown_result,
        )
