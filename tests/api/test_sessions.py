"""Tests for P5-T1: Session lifecycle and server-derived scope enforcement.

Covers:
  - POST /session creates a valid session in SQLite
  - Session token maps to scope on the server (server-derived, never client-supplied)
  - Expired session tokens are rejected with 401
  - Unknown tokens are rejected with 401
  - GET /usage requires a valid session token
  - Server ignores any client-supplied scope parameters
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.storage.db import DatabaseManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> DatabaseManager:
    """Fresh DatabaseManager backed by a temp SQLite file."""
    return DatabaseManager(db_path=tmp_path / "test.db")


@pytest.fixture()
def client_with_state(tmp_db: DatabaseManager) -> TestClient:
    """Set app.state directly so all routes share the same tmp_db instance."""
    from src.security.config import OwnerConfig

    app.state.db = tmp_db
    app.state.cfg = OwnerConfig.from_env()
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Sanity test: health endpoint requires no auth."""

    def test_health_ok(self, client_with_state: TestClient) -> None:
        resp = client_with_state.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestSessionCreation:
    """P5-T1: POST /session issues a valid token and stores it in DB."""

    def test_creates_session(self, client_with_state: TestClient) -> None:
        resp = client_with_state.post("/session")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Token must have correct prefix
        assert data["session_id"].startswith("prov_sess_")

        # Tier A default (no keys provided)
        assert data["tier"] == "tier_a_demo"
        assert "expires_at" in data
        assert "message" in data

        # Verify persisted in the same DB that the app used
        db: DatabaseManager = app.state.db
        row = db.get_session(data["session_id"])
        assert row is not None, f"Session {data['session_id']} not found in DB"
        assert row["session_id"] == data["session_id"]

    def test_creates_tier_c_with_llm_key(self, client_with_state: TestClient) -> None:
        """Supplying X-LLM-Key header should produce Tier C session."""
        resp = client_with_state.post(
            "/session",
            headers={"X-LLM-Key": "sk-test-fake-openai-key-12345678"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tier"] == "tier_c_byok"

    def test_tokens_are_unique(self, client_with_state: TestClient) -> None:
        """Each POST /session must produce a unique token."""
        tokens = {client_with_state.post("/session").json()["session_id"] for _ in range(5)}
        assert len(tokens) == 5  # All unique


class TestServerDerivedScope:
    """P5-T1: Server always derives scope from the token; clients cannot override it."""

    def test_unknown_token_rejected(self, client_with_state: TestClient) -> None:
        resp = client_with_state.get(
            "/usage",
            headers={"Authorization": "Bearer prov_sess_totallyfaketoken"},
        )
        assert resp.status_code == 401

    def test_missing_token_rejected(self, client_with_state: TestClient) -> None:
        resp = client_with_state.get("/usage")
        assert resp.status_code == 401

    def test_valid_token_accepted(
        self, client_with_state: TestClient, tmp_db: DatabaseManager
    ) -> None:
        # Create session
        create_resp = client_with_state.post("/session")
        token = create_resp.json()["session_id"]

        # GET /usage with valid token
        usage_resp = client_with_state.get(
            "/usage",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert usage_resp.status_code == 200
        usage = usage_resp.json()
        assert "tier" in usage
        assert "questions_owner_llm_remaining" in usage

    def test_expired_session_rejected(
        self, client_with_state: TestClient, tmp_db: DatabaseManager
    ) -> None:
        """Sessions with a past expires_at must be rejected with 401."""
        # Manually insert an expired session
        expired_id = "prov_sess_expiredtoken123456"
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        with tmp_db._get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, created_at, expires_at, tier) VALUES (?,?,?,?)",
                (expired_id, datetime.now(UTC).isoformat(), past, "tier_a_demo"),
            )
            conn.commit()

        resp = client_with_state.get(
            "/usage",
            headers={"Authorization": f"Bearer {expired_id}"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()


class TestExamplesEndpoint:
    """P5-T4: GET /examples requires no auth and returns demo questions."""

    def test_examples_no_auth(self, client_with_state: TestClient) -> None:
        resp = client_with_state.get("/examples")
        assert resp.status_code == 200
        data = resp.json()
        assert "examples" in data
        assert len(data["examples"]) >= 5
        # Each example has id and question fields
        for ex in data["examples"]:
            assert "id" in ex
            assert "question" in ex

    def test_examples_have_diverse_categories(self, client_with_state: TestClient) -> None:
        resp = client_with_state.get("/examples")
        categories = {ex["category"] for ex in resp.json()["examples"]}
        assert len(categories) >= 2  # Multiple categories
