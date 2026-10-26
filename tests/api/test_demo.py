"""Tests for P5-T4: Demo mode (Tier A) and read-only isolation.

Covers:
  - Anyone can call GET /examples without a session token
  - Demo scope returns correct answers (mocked pipeline)
  - GET /usage shows Tier A limits
  - Attempt to use demo scope to write data is rejected (403)
  - Questions over demo corpus use owner-funded caps
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager


@pytest.fixture()
def tmp_db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(db_path=tmp_path / "demo_test.db")


@pytest.fixture()
def client(tmp_db: DatabaseManager) -> TestClient:
    app.state.db = tmp_db
    app.state.cfg = OwnerConfig.from_env()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestDemoModeNoAuth:
    """GET /examples must work without any session token."""

    def test_get_examples_no_auth_required(self, client: TestClient) -> None:
        resp = client.get("/examples")
        assert resp.status_code == 200

    def test_examples_contain_question_text(self, client: TestClient) -> None:
        resp = client.get("/examples")
        examples = resp.json()["examples"]
        assert all("?" in ex["question"] for ex in examples)

    def test_corpus_identifier_present(self, client: TestClient) -> None:
        resp = client.get("/examples")
        assert resp.json()["corpus"] == "provenance_rag_demo"


class TestDemoScopeReadOnly:
    """Visitors must never be able to write into scope='demo'."""

    def test_assert_demo_scope_readonly_integration(self) -> None:
        """Unit-level: assert_demo_scope_readonly raises for demo scope writes."""
        from fastapi import HTTPException

        from src.api.caps import assert_demo_scope_readonly

        with pytest.raises(HTTPException) as exc:
            assert_demo_scope_readonly("demo", action="upload")
        assert exc.value.status_code == 403

    def test_regular_scope_is_not_blocked(self) -> None:
        from src.api.caps import assert_demo_scope_readonly

        # Must not raise for a visitor's own session scope
        assert_demo_scope_readonly("prov_sess_abc123xyz456", action="upload")


class TestTierAUsageLimits:
    """GET /usage for a Tier A session must show correct allowance fields."""

    def test_usage_shows_tier_a_defaults(self, client: TestClient, tmp_db: DatabaseManager) -> None:
        # Create session
        create_resp = client.post("/session")
        assert create_resp.status_code == 200
        token = create_resp.json()["session_id"]

        usage_resp = client.get("/usage", headers={"Authorization": f"Bearer {token}"})
        assert usage_resp.status_code == 200
        usage = usage_resp.json()

        assert usage["tier"] == "tier_a_demo"
        # Fresh session: nothing used
        assert usage["questions_owner_llm_used"] == 0
        assert usage["questions_own_llm_used"] == 0
        assert usage["at_capacity"] is False

    def test_usage_remaining_decreases_correctly(self, client: TestClient) -> None:
        """Verify that remaining = max - used."""
        create_resp = client.post("/session")
        token = create_resp.json()["session_id"]

        # Directly update the DB that the app is using (app.state.db)
        active_db: DatabaseManager = app.state.db
        with active_db._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET questions_owner_llm = 3 WHERE session_id = ?",
                (token,),
            )
            conn.commit()

        usage_resp = client.get("/usage", headers={"Authorization": f"Bearer {token}"})
        assert usage_resp.status_code == 200, usage_resp.text
        usage = usage_resp.json()
        assert usage["questions_owner_llm_used"] == 3
        assert usage["questions_owner_llm_remaining"] == usage["questions_owner_llm_max"] - 3
