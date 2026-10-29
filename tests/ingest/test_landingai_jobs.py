"""Landing AI Parse Jobs (standard tier) + actual billing extraction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pymupdf
import pytest

from src.ingest.parsers.landingai import (
    LandingAIAdapter,
    LandingAINormalizer,
    extract_landing_credit_units,
)
from src.ingest.parsers.structured_doc import BlockType
from src.security.credit_config import LANDING_JOBS_CREATE_URL, LANDING_SERVICE_TIER
from src.security.secret import Secret


def test_extract_landing_credit_units_from_metadata() -> None:
    payload = {
        "status": "completed",
        "result": {
            "markdown": "# Hello",
            "metadata": {
                "billing": {"service_tier": "standard", "total_credits": 1.1},
                "page_count": 1,
            },
        },
    }
    assert extract_landing_credit_units(payload) == 11


def test_extract_landing_credit_units_missing_returns_none() -> None:
    assert extract_landing_credit_units({"result": {"markdown": "x"}}) is None


def test_landingai_normalizer_v2_structure() -> None:
    payload = {
        "markdown": "# Title\n\nBody",
        "structure": {
            "type": "document",
            "children": [
                {
                    "type": "page",
                    "grounding": {"page": 1},
                    "children": [
                        {
                            "type": "heading",
                            "markdown": "# Title",
                            "grounding": {"page": 1, "box": {"xmin": 0, "ymin": 1, "xmax": 2, "ymax": 3}},
                        },
                        {
                            "type": "text",
                            "markdown": "Body paragraph",
                            "grounding": {"page": 1, "box": [10, 20, 30, 40]},
                        },
                    ],
                }
            ],
        },
    }
    blocks = LandingAINormalizer.parse_payload_to_blocks(payload)
    assert blocks[0].type == BlockType.HEADING
    assert blocks[1].type == BlockType.PARAGRAPH
    assert blocks[1].text == "Body paragraph"


def _tiny_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), "Hello world", fontsize=12)
    path.write_bytes(doc.tobytes())
    doc.close()
    return path


@pytest.mark.asyncio
async def test_landing_adapter_parse_jobs_standard_tier(tmp_path: Path) -> None:
    pdf_path = _tiny_pdf(tmp_path / "doc.pdf")
    adapter = LandingAIAdapter()

    create_resp = MagicMock()
    create_resp.status_code = 202
    create_resp.json.return_value = {"job_id": "parse-1", "status": "pending"}

    poll_resp = MagicMock()
    poll_resp.status_code = 200
    poll_resp.json.return_value = {
        "status": "completed",
        "result": {
            "markdown": "# Hello world",
            "metadata": {
                "page_count": 1,
                "model_version": "dpt-3-verity-latest",
                "billing": {"service_tier": "standard", "total_credits": 0.4},
                "failed_pages": [],
            },
            "chunks": [
                {
                    "type": "text",
                    "markdown": "# Hello world",
                    "grounding": {"page": 1, "box": [0, 0, 1, 1]},
                }
            ],
        },
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.post = AsyncMock(return_value=create_resp)
    mock_client.get = AsyncMock(return_value=poll_resp)

    with patch("src.ingest.parsers.landingai.create_secure_client", return_value=mock_client):
        doc = await adapter.parse(
            pdf_path,
            api_key=Secret("land_test_key"),
            model="dpt-3-verity-latest",
        )

    assert doc.credits_units == 4
    assert doc.parser_used == "landingai"
    post_call = mock_client.post.await_args
    assert str(post_call.args[0]) == LANDING_JOBS_CREATE_URL
    assert post_call.kwargs["data"]["service_tier"] == LANDING_SERVICE_TIER
    assert post_call.kwargs["data"]["model"] == "dpt-3-verity-latest"
    mock_client.get.assert_awaited()
