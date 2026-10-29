"""Unit and integration tests for React Frontend SPA mounting and asset serving."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_react_index_serving(client: TestClient) -> None:
    """Verify GET / returns 200 and serves the compiled React single-page application."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "Provenance RAG" in html
    assert 'id="root"' in html
    assert "/assets/" in html


def test_react_assets_serving(client: TestClient) -> None:
    """Verify all bundled Vite JavaScript and CSS assets referenced in index.html are reachable."""
    index_res = client.get("/")
    assert index_res.status_code == 200
    html = index_res.text

    # Extract asset paths like /assets/index-*.css and /assets/index-*.js
    assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
    assert len(assets) >= 2, f"Expected at least CSS and JS asset, found: {assets}"

    for asset_path in assets:
        res = client.get(asset_path)
        assert res.status_code == 200
        assert len(res.content) > 100


def test_api_routes_not_shadowed(client: TestClient) -> None:
    """Verify standard API endpoints still take routing precedence over static files."""
    # Health probe
    res_health = client.get("/health")
    assert res_health.status_code == 200
    health = res_health.json()
    assert health["status"] == "ok"
    assert health["version"] == "1.0.0"

    # Examples endpoint
    res_examples = client.get("/examples")
    assert res_examples.status_code == 200
    assert "examples" in res_examples.json()


def test_demo_corpus_pdf_preview_served(client: TestClient) -> None:
    """Tier A iframe previews are served from demo_corpus/, not the old SPA copies."""
    res = client.get("/demo_corpus/Apple-Annual-Report-2023.pdf")
    assert res.status_code == 200
    assert "pdf" in res.headers.get("content-type", "").lower()
    assert res.content[:5] == b"%PDF-"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in res.headers.get("Content-Security-Policy", "")

    missing = client.get("/demo_corpus/us_constitution_bill_of_rights.pdf")
    assert missing.status_code == 404

    not_pdf = client.get("/demo_corpus/example_questions.json")
    assert not_pdf.status_code == 404
