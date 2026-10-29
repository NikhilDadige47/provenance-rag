"""Landing AI DPT-3 adapter: Parse Jobs on the standard tier.

Sync Parse always bills at the priority (2x) rate. This adapter submits
async Parse Jobs with service_tier=standard, polls to completion, and
records metadata.billing.total_credits so the ledger can commit actuals.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import httpx

from src.ingest.estimator import InputRejectedError
from src.ingest.parsers.cleanup import clean_blocks
from src.ingest.parsers.structured_doc import Block, BlockType, StructuredDoc
from src.interfaces import IParser
from src.security.credit_config import (
    LANDING_JOBS_CREATE_URL,
    LANDING_JOBS_GET_URL,
    LANDING_MODELS,
    LANDING_SERVICE_TIER,
    landing_credits_to_units,
)
from src.security.egress import create_secure_client
from src.security.errors import (
    InvalidKeyError,
    KeySecurityError,
    ProviderTimeoutError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.security.secret import Secret

_INPUT_JOB_ERROR_CODES = frozenset(
    {
        "invalid_document",
        "unsupported_file_type",
        "password_protected",
        "encrypted",
        "too_many_pages",
        "file_too_large",
    }
)


def extract_landing_credit_units(payload: dict[str, Any]) -> int | None:
    """Read metadata.billing.total_credits from a Parse or Parse Jobs payload."""
    metadata = _metadata_from_payload(payload)
    billing = metadata.get("billing") if isinstance(metadata, dict) else None
    if not isinstance(billing, dict):
        return None
    raw = billing.get("total_credits")
    if raw is None:
        return None
    try:
        return landing_credits_to_units(float(raw))
    except (TypeError, ValueError):
        return None


def _metadata_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("metadata"), dict):
        return payload["metadata"]
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("metadata"), dict):
        return result["metadata"]
    return {}


def _result_from_job(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if isinstance(result, dict) and (result.get("markdown") or result.get("structure") or result.get("chunks")):
        return result
    if payload.get("markdown") or payload.get("chunks") or payload.get("structure"):
        return payload
    return {}


def _box_to_list(raw_box: Any) -> list[float] | None:
    if isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
        return [float(coord) for coord in raw_box]
    if isinstance(raw_box, dict):
        if "xmin" in raw_box or "ymin" in raw_box:
            return [
                float(raw_box.get("ymin", 0)),
                float(raw_box.get("xmin", 0)),
                float(raw_box.get("ymax", 0)),
                float(raw_box.get("xmax", 0)),
            ]
        return [
            float(raw_box.get("top", 0)),
            float(raw_box.get("left", 0)),
            float(raw_box.get("bottom", 0)),
            float(raw_box.get("right", 0)),
        ]
    return None


class LandingAINormalizer:
    """Normalizes Landing AI ADE v1 chunks and DPT-3 v2 structure into StructuredDoc."""

    @classmethod
    def parse_payload_to_blocks(cls, payload: dict[str, Any]) -> list[Block]:
        """Convert a Parse payload (v1 chunks or v2 structure/markdown) into blocks."""
        result = _result_from_job(payload) or payload
        chunks = result.get("chunks") or payload.get("chunks") or []
        if chunks:
            return cls._blocks_from_chunks(chunks)

        structure = result.get("structure") or payload.get("structure")
        if isinstance(structure, dict):
            blocks = cls._blocks_from_structure(structure)
            if blocks:
                return blocks

        markdown = result.get("markdown") or payload.get("markdown")
        if markdown:
            from src.ingest.parsers.llamaparse import LlamaParseNormalizer

            return LlamaParseNormalizer.parse_markdown_to_blocks(str(markdown))
        return []

    @classmethod
    def _blocks_from_chunks(cls, chunks: list[Any]) -> list[Block]:
        blocks: list[Block] = []
        for idx, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                continue
            block = cls._block_from_node(
                node_type=str(chunk.get("type", "text")).lower(),
                text=str(chunk.get("markdown") or chunk.get("text") or "").strip(),
                grounding=chunk.get("grounding") or {},
                order=idx,
            )
            if block:
                blocks.append(block)
        return blocks

    @classmethod
    def _blocks_from_structure(cls, structure: dict[str, Any]) -> list[Block]:
        blocks: list[Block] = []

        def walk(node: Any, inherited_page: int) -> None:
            if not isinstance(node, dict):
                return
            node_type = str(node.get("type", "")).lower()
            grounding = node.get("grounding") or {}
            page = inherited_page
            raw_page = grounding.get("page") if isinstance(grounding, dict) else None
            if raw_page is not None:
                try:
                    page = max(1, int(raw_page) + (1 if int(raw_page) == 0 else 0))
                    if int(raw_page) >= 1:
                        page = int(raw_page)
                except (TypeError, ValueError):
                    page = inherited_page

            if node_type not in {"document", "page", ""}:
                block = cls._block_from_node(
                    node_type=node_type,
                    text=str(node.get("markdown") or node.get("text") or "").strip(),
                    grounding=grounding if isinstance(grounding, dict) else {},
                    order=len(blocks),
                    page_override=page,
                )
                if block:
                    blocks.append(block)

            for child in node.get("children") or []:
                walk(child, page)

        walk(structure, 1)
        return blocks

    @classmethod
    def _block_from_node(
        cls,
        node_type: str,
        text: str,
        grounding: dict[str, Any],
        order: int,
        page_override: int | None = None,
    ) -> Block | None:
        text = text.strip()
        if not text:
            return None

        raw_page = grounding.get("page") if grounding else None
        if page_override is not None:
            page = page_override
        elif raw_page is None:
            page = 1
        else:
            try:
                page = max(1, int(raw_page))
            except (TypeError, ValueError):
                page = 1

        bbox = _box_to_list(grounding.get("box") if grounding else None)

        if node_type == "table" or text.startswith("|"):
            b_type = BlockType.TABLE
            level = None
        elif node_type in {"heading", "title"} or text.startswith("#"):
            b_type = BlockType.HEADING
            hashes = len(text.split()[0]) if text.startswith("#") else 2
            level = min(6, hashes) if text.startswith("#") else 2
            text = text.lstrip("#").strip()
        elif node_type in {"figure", "image"}:
            b_type = BlockType.FIGURE
            level = None
        elif node_type in {"list", "list_item"} or text.startswith(("- ", "* ", "+ ", "• ")):
            b_type = BlockType.LIST_ITEM
            level = None
        else:
            b_type = BlockType.PARAGRAPH
            level = None

        if not text:
            return None
        return Block(
            type=b_type,
            text=text,
            level=level,
            page=page,
            bbox=bbox,
            order=order,
        )


class LandingAIAdapter(IParser):
    """Adapter for Landing AI DPT-3 Parse Jobs (standard tier)."""

    @property
    def name(self) -> str:
        return "landingai"

    @property
    def requires_key(self) -> bool:
        return True

    async def parse(
        self,
        file_path: Path,
        api_key: Secret | None = None,
        *,
        model: str | None = None,
        service_tier: str = LANDING_SERVICE_TIER,
    ) -> StructuredDoc:
        """Submit a standard-tier Parse Job, poll, and return a billed StructuredDoc."""
        if not api_key or not api_key.reveal():
            raise KeySecurityError("Landing AI requires an API key, but none was provided.")

        headers = {"Authorization": f"Bearer {api_key.reveal()}"}
        resolved_model = model or LANDING_MODELS["verity"]
        job_payload: dict[str, Any] = {}

        async with create_secure_client() as client:
            try:
                with open(file_path, "rb") as handle:
                    files = {"document": (file_path.name, handle, "application/pdf")}
                    data = {
                        "model": resolved_model,
                        "service_tier": service_tier,
                    }
                    create_resp = await client.post(
                        LANDING_JOBS_CREATE_URL,
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=45.0,
                    )
                self._raise_for_status(create_resp)
                created = create_resp.json()
                if created.get("status") == "completed" and (
                    created.get("result") or created.get("markdown")
                ):
                    job_payload = created
                else:
                    job_id = created.get("job_id") or created.get("id")
                    if not job_id:
                        raise RuntimeError("Landing AI Parse Jobs did not return a job_id.")
                    job_payload = await self._poll_job(client, str(job_id), headers)
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError(provider=self.name) from exc

        result = _result_from_job(job_payload) or job_payload
        metadata = _metadata_from_payload(job_payload)
        credits_units = extract_landing_credit_units(job_payload)
        failed_pages_raw = metadata.get("failed_pages") or []
        failed_pages = [int(p) for p in failed_pages_raw if str(p).isdigit() or isinstance(p, int)]

        blocks = LandingAINormalizer.parse_payload_to_blocks(job_payload)
        meta_pages = metadata.get("page_count")
        try:
            total_pages = max(int(meta_pages), 1) if meta_pages is not None else 1
        except (TypeError, ValueError):
            total_pages = 1
        if blocks:
            total_pages = max(total_pages, max(b.page for b in blocks))
        cleaned = clean_blocks(blocks, total_pages=total_pages)

        return StructuredDoc(
            doc_id=f"doc_{uuid.uuid4().hex[:12]}",
            title=file_path.stem.replace("_", " ").title(),
            page_count=total_pages,
            parser_used=self.name,
            parser_version=str(metadata.get("model_version") or resolved_model),
            blocks=cleaned,
            raw_text=result.get("markdown"),
            credits_units=credits_units,
            failed_pages=failed_pages,
        )

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise InvalidKeyError(provider=self.name, is_visitor_key=True)
        if response.status_code == 402:
            raise QuotaExhaustedError(provider=self.name, is_visitor_key=True)
        if response.status_code == 422:
            detail = ""
            try:
                detail = str(response.json())
            except Exception:
                detail = response.text[:200]
            raise InputRejectedError(f"Landing AI rejected the document: {detail}")
        if response.status_code == 429:
            raise RateLimitedError(provider=self.name, is_visitor_key=True)
        if response.status_code not in {200, 201, 202, 206}:
            response.raise_for_status()

    async def _poll_job(
        self,
        client: httpx.AsyncClient,
        job_id: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        delay = 0.75
        url = f"{LANDING_JOBS_GET_URL}/{job_id}"
        for _ in range(60):
            poll_resp = await client.get(url, headers=headers, timeout=30.0)
            self._raise_for_status(poll_resp)
            body = poll_resp.json()
            status = str(body.get("status") or "").lower()
            if status == "completed":
                return body
            if status == "failed":
                error = body.get("error") or {}
                code = str(error.get("code") or "").lower()
                message = str(error.get("message") or "Parse job failed")
                if code in _INPUT_JOB_ERROR_CODES:
                    raise InputRejectedError(f"Landing AI job failed: {message}")
                raise RuntimeError(f"Landing AI job failed: {message}")
            await asyncio.sleep(delay)
            delay = min(delay * 1.4, 5.0)
        raise ProviderTimeoutError(provider=self.name)
