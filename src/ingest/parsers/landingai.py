"""Landing AI ADE adapter and normalizer.

Leverages Landing AI Agentic Document Extraction (ADE) to parse PDFs into
grounded chunks with spatial coordinates (bounding boxes) and Markdown text.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from src.ingest.parsers.cleanup import clean_blocks
from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc
from src.interfaces import IParser
from src.security.egress import create_secure_client
from src.security.errors import (
    InvalidKeyError,
    KeySecurityError,
    ProviderTimeoutError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.security.secret import Secret

LANDINGAI_PARSE_URL = "https://api.va.landing.ai/v1/ade/parse"


class LandingAINormalizer:
    """Normalizes Landing AI ADE chunks and grounding metadata into StructuredDoc."""

    @classmethod
    def parse_payload_to_blocks(cls, payload: dict[str, Any]) -> list[Block]:
        """Convert Landing AI ADE chunks payload into a list of Block objects."""
        chunks = payload.get("chunks", [])
        if not chunks and "markdown" in payload:
            # Fallback if only raw markdown is returned
            from src.ingest.parsers.llamaparse import LlamaParseNormalizer

            return LlamaParseNormalizer.parse_markdown_to_blocks(payload["markdown"])

        blocks: list[Block] = []

        for idx, chunk in enumerate(chunks):
            chunk_type = chunk.get("type", "text").lower()
            text = chunk.get("markdown") or chunk.get("text", "")
            text = text.strip()
            if not text:
                continue

            grounding = chunk.get("grounding", {}) or {}
            raw_page = grounding.get("page")
            if raw_page is None:
                page = 1
            else:
                try:
                    # Landing AI ADE grounding.page may be 0; clamp to at least 1 for Block schema (ge=1)
                    page = max(1, int(raw_page))
                except (ValueError, TypeError):
                    page = 1
            raw_box = grounding.get("box")

            bbox: list[float] | None = None
            if isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
                bbox = [float(coord) for coord in raw_box]
            elif isinstance(raw_box, dict):
                bbox = [
                    float(raw_box.get("top", 0)),
                    float(raw_box.get("left", 0)),
                    float(raw_box.get("bottom", 0)),
                    float(raw_box.get("right", 0)),
                ]

            # Determine semantic block type
            if chunk_type == "table" or text.startswith("|"):
                b_type = BlockType.TABLE
                level = None
            elif text.startswith("#"):
                b_type = BlockType.HEADING
                level = min(6, len(text.split()[0])) if text.startswith("#") else 2
                # Strip leading hashes from heading text if present
                text = text.lstrip("#").strip()
            elif chunk_type in {"figure", "image"}:
                b_type = BlockType.FIGURE
                level = None
            elif text.startswith(("- ", "* ", "+ ", "• ")):
                b_type = BlockType.LIST_ITEM
                level = None
            else:
                b_type = BlockType.PARAGRAPH
                level = None

            blocks.append(
                Block(
                    type=b_type,
                    text=text,
                    level=level,
                    page=page,
                    bbox=bbox,
                    order=idx,
                )
            )

        return blocks


class LandingAIAdapter(IParser):
    """Adapter for Landing AI's ADE service."""

    @property
    def name(self) -> str:
        return "landingai"

    @property
    def requires_key(self) -> bool:
        return True

    async def parse(self, file_path: Path, api_key: Secret | None = None) -> StructuredDoc:
        """Call Landing AI ADE API with visitor key and return StructuredDoc."""
        if not api_key or not api_key.reveal():
            raise KeySecurityError("Landing AI requires an API key, but none was provided.")

        headers = {
            "Authorization": f"Bearer {api_key.reveal()}",
        }

        async with create_secure_client() as client:
            try:
                with open(file_path, "rb") as f:
                    files = {"document": (file_path.name, f, "application/pdf")}
                    response = await client.post(
                        LANDINGAI_PARSE_URL,
                        headers=headers,
                        files=files,
                        timeout=45.0,
                    )

                if response.status_code in {401, 403}:
                    raise InvalidKeyError(provider=self.name, is_visitor_key=True)
                if response.status_code == 402:
                    raise QuotaExhaustedError(provider=self.name, is_visitor_key=True)
                if response.status_code == 429:
                    raise RateLimitedError(provider=self.name, is_visitor_key=True)
                response.raise_for_status()

                payload = response.json()

            except httpx.TimeoutException:
                raise ProviderTimeoutError(provider=self.name) from None

        blocks = LandingAINormalizer.parse_payload_to_blocks(payload)
        total_pages = max([b.page for b in blocks], default=1)
        cleaned = clean_blocks(blocks, total_pages=total_pages)

        return StructuredDoc(
            doc_id=f"doc_{uuid.uuid4().hex[:12]}",
            title=file_path.stem.replace("_", " ").title(),
            page_count=total_pages,
            parser_used=self.name,
            parser_version="landingai-ade-v2",
            blocks=cleaned,
            raw_text=payload.get("markdown"),
        )
