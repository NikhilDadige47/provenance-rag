"""P9-T4 / P9-T5: security headers, metrics privacy, call-site review."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

ALLOWED_GENERATE_STREAM = {
    SRC / "generation" / "llm.py",
    SRC / "generation" / "rewrite.py",
    SRC / "api" / "chat.py",
    SRC / "cli.py",
    SRC / "interfaces.py",
}

ALLOWED_EMBED_DOCUMENTS = {
    SRC / "retrieval" / "embed.py",
    SRC / "api" / "jobs.py",
}

ALLOWED_COHERE_EMBEDDER = {
    SRC / "retrieval" / "embed.py",
    SRC / "retrieval" / "search.py",
    SRC / "retrieval" / "__init__.py",
    SRC / "api" / "jobs.py",
}


def test_production_health_returns_503_when_not_ready(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("QDRANT_URL", ":memory:")

    class DeadStore:
        def ping(self) -> bool:
            return False

    with TestClient(app) as client:
        cfg = getattr(app.state, "cfg", None)
        assert cfg is not None
        previous_env = cfg.app_env
        previous_store = getattr(app.state, "store", None)
        cfg.app_env = "production"
        app.state.store = DeadStore()
        try:
            health = client.get("/health")
            assert health.status_code == 503
            body = health.json()
            assert body["ready"] is False
            assert body["status"] == "ok"
        finally:
            cfg.app_env = previous_env
            app.state.store = previous_store


def test_health_and_security_headers() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"
    assert "X-Content-Type-Options" in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in resp.headers
    assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"] or resp.headers[
        "X-Frame-Options"
    ] == "DENY"
    assert "frame-src 'self' blob:" in resp.headers["Content-Security-Policy"]


def test_metrics_have_no_content_fields() -> None:
    client = TestClient(app)
    client.get("/health")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    payload = resp.json()
    blob = str(payload).lower()
    assert "requests" in payload
    assert "daily_spend" in payload
    for banned in ("question", "prompt", "api_key", "sk-", "gsk_"):
        assert banned not in blob


def test_session_sets_httponly_cookie() -> None:
    client = TestClient(app)
    resp = client.post("/session")
    assert resp.status_code == 200
    cookie = (resp.headers.get("set-cookie") or "").lower()
    assert "session_token=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_production_https_and_hsts() -> None:
    client = TestClient(app)
    cfg = getattr(app.state, "cfg", None)
    if cfg is None:
        client.get("/health")
        cfg = getattr(app.state, "cfg", None)
    assert cfg is not None
    previous = cfg.app_env
    cfg.app_env = "production"
    try:
        health = client.get("/health")
        assert health.status_code == 200
        blocked = client.get("/metrics")
        assert blocked.status_code == 403
        assert "https" in blocked.json()["detail"].lower()
        allowed = client.get("/metrics", headers={"X-Forwarded-Proto": "https"})
        assert allowed.status_code == 200
        assert "strict-transport-security" in {k.lower() for k in allowed.headers}
        assert "max-age" in allowed.headers["strict-transport-security"].lower()
    finally:
        cfg.app_env = previous


def test_terms_endpoint_is_public() -> None:
    client = TestClient(app)
    resp = client.get("/terms")
    assert resp.status_code == 200
    text = resp.content.decode("utf-8", errors="replace").lower()
    assert "right to upload" in text
    assert "cohere" in text
    assert "ttl" in text


def _py_files() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if p.is_file()]


def test_generate_stream_only_on_gated_paths() -> None:
    offenders: list[str] = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        if "generate_stream(" not in text:
            continue
        if path.resolve() not in {p.resolve() for p in ALLOWED_GENERATE_STREAM}:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_embed_documents_only_on_gated_paths() -> None:
    offenders: list[str] = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        if "embed_documents(" not in text:
            continue
        if path.resolve() not in {p.resolve() for p in ALLOWED_EMBED_DOCUMENTS}:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_cohere_embedder_construction_allowlist() -> None:
    offenders: list[str] = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        if "CohereEmbedder(" not in text:
            continue
        if path.resolve() not in {p.resolve() for p in ALLOWED_COHERE_EMBEDDER}:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
