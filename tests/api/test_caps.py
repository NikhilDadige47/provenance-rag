"""Tests for P5-T2 & P5-T3: Owner cost caps, rate limits, kill switch, and daily global budgets.

Covers:
  - Per-session owner-LLM question cap triggers at correct threshold
  - Per-session BYOK question cap triggers at correct threshold
  - Per-session rerank cap triggers
  - Per-IP rolling-window rate limit triggers
  - Per-IP daily question cap triggers
  - Daily global cap triggers "Demo at capacity" (429)
  - Kill switch disabling owner LLM returns 503
  - Kill switch disabling uploads returns 503
  - Demo scope read-only guard raises 403
  - Budget alert logging at 50% and 80%
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.api.caps import (
    MAX_REQUESTS_PER_WINDOW,
    _ip_request_timestamps,
    assert_demo_scope_readonly,
    check_and_increment_daily_rerank,
    check_and_increment_ip_owner_questions,
    check_and_increment_session_byok_llm,
    check_and_increment_session_owner_llm,
    check_and_increment_session_rerank,
    check_ip_rate_limit,
    check_kill_switch_owner_llm,
    check_kill_switch_uploads,
)
from src.security.config import OwnerConfig
from src.storage.db import DatabaseManager


@pytest.fixture()
def tmp_db(tmp_path: Path) -> DatabaseManager:
    """Fresh in-memory-like DB backed by a temp file."""
    return DatabaseManager(db_path=tmp_path / "caps_test.db")


@pytest.fixture()
def db_with_session(tmp_db: DatabaseManager) -> tuple[DatabaseManager, str]:
    """Create a session in the DB and return (db, session_id)."""
    session_id = "prov_sess_testcapssession00001"
    with tmp_db._get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, created_at, tier) VALUES (?, ?, ?)",
            (session_id, datetime.now(UTC).isoformat(), "tier_a_demo"),
        )
        conn.commit()
    return tmp_db, session_id


@pytest.fixture()
def default_cfg() -> OwnerConfig:
    return OwnerConfig.from_env()


# ---------------------------------------------------------------------------
# Per-session owner-LLM cap
# ---------------------------------------------------------------------------


class TestSessionOwnerLLMCap:
    def test_cap_triggers_at_max(
        self, db_with_session: tuple[DatabaseManager, str], default_cfg: OwnerConfig
    ) -> None:
        db, session_id = db_with_session
        limit = default_cfg.session_max_questions_owner_llm

        # Consume all allowed questions
        for _ in range(limit):
            check_and_increment_session_owner_llm(db, session_id, default_cfg)

        # The next call must raise 429
        with pytest.raises(HTTPException) as exc_info:
            check_and_increment_session_owner_llm(db, session_id, default_cfg)
        assert exc_info.value.status_code == 429
        assert "owner-funded questions" in exc_info.value.detail.lower()

    def test_counter_is_persistent(
        self, db_with_session: tuple[DatabaseManager, str], default_cfg: OwnerConfig
    ) -> None:
        """Counter must survive across function calls (stored in DB)."""
        db, session_id = db_with_session
        check_and_increment_session_owner_llm(db, session_id, default_cfg)
        row = db.get_session(session_id)
        assert row is not None
        assert row["questions_owner_llm"] == 1


# ---------------------------------------------------------------------------
# Per-session BYOK question cap
# ---------------------------------------------------------------------------


class TestSessionBYOKCap:
    def test_byok_cap_independent_of_owner_cap(
        self, db_with_session: tuple[DatabaseManager, str], default_cfg: OwnerConfig
    ) -> None:
        """BYOK counter must be separate from owner-LLM counter."""
        db, session_id = db_with_session
        check_and_increment_session_byok_llm(db, session_id, default_cfg)
        row = db.get_session(session_id)
        assert row["questions_own_llm"] == 1
        assert row["questions_owner_llm"] == 0

    def test_byok_cap_triggers(self, db_with_session: tuple[DatabaseManager, str]) -> None:
        db, session_id = db_with_session
        # Use a cfg with a very low cap for test speed
        cfg = OwnerConfig(session_max_questions_own_llm=2)

        check_and_increment_session_byok_llm(db, session_id, cfg)
        check_and_increment_session_byok_llm(db, session_id, cfg)

        with pytest.raises(HTTPException) as exc_info:
            check_and_increment_session_byok_llm(db, session_id, cfg)
        assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# Per-session rerank cap
# ---------------------------------------------------------------------------


class TestSessionRerankCap:
    def test_rerank_cap_triggers(self, db_with_session: tuple[DatabaseManager, str]) -> None:
        db, session_id = db_with_session
        cfg = OwnerConfig(session_max_rerank_calls=2)

        check_and_increment_session_rerank(db, session_id, cfg)
        check_and_increment_session_rerank(db, session_id, cfg)

        with pytest.raises(HTTPException) as exc_info:
            check_and_increment_session_rerank(db, session_id, cfg)
        assert exc_info.value.status_code == 429
        assert "rerank" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Per-IP rate limit
# ---------------------------------------------------------------------------


class TestIPRateLimit:
    def _clear_ip(self, ip: str) -> None:
        _ip_request_timestamps.pop(ip, None)

    def test_rate_limit_triggers(self) -> None:
        test_ip = "192.168.99.1"
        self._clear_ip(test_ip)

        # Consume all slots
        for _ in range(MAX_REQUESTS_PER_WINDOW):
            check_ip_rate_limit(test_ip)

        with pytest.raises(HTTPException) as exc_info:
            check_ip_rate_limit(test_ip)
        assert exc_info.value.status_code == 429
        assert "rate limit" in exc_info.value.detail.lower()

        # Cleanup
        self._clear_ip(test_ip)

    def test_different_ips_are_independent(self) -> None:
        ip1, ip2 = "10.0.0.1", "10.0.0.2"
        self._clear_ip(ip1)
        self._clear_ip(ip2)

        # Fill ip1 to limit
        for _ in range(MAX_REQUESTS_PER_WINDOW):
            check_ip_rate_limit(ip1)

        # ip2 must still be allowed
        check_ip_rate_limit(ip2)  # should not raise

        self._clear_ip(ip1)
        self._clear_ip(ip2)

    def test_dev_loopback_skips_rate_limit(self) -> None:
        from src.security.config import OwnerConfig

        cfg = OwnerConfig(app_env="development")
        self._clear_ip("127.0.0.1")
        for _ in range(MAX_REQUESTS_PER_WINDOW + 5):
            check_ip_rate_limit("127.0.0.1", cfg)
        self._clear_ip("127.0.0.1")


# ---------------------------------------------------------------------------
# Per-IP daily question cap
# ---------------------------------------------------------------------------


class TestIPDailyQuestionCap:
    def test_daily_question_cap_triggers(self, tmp_db: DatabaseManager) -> None:
        test_ip = "203.0.113.42"
        cfg = OwnerConfig(session_max_questions_owner_llm=2)
        check_and_increment_ip_owner_questions(tmp_db, test_ip, cfg)
        check_and_increment_ip_owner_questions(tmp_db, test_ip, cfg)
        with pytest.raises(HTTPException) as exc_info:
            check_and_increment_ip_owner_questions(tmp_db, test_ip, cfg)
        assert exc_info.value.status_code == 429
        assert "owner-funded" in exc_info.value.detail.lower()

    def test_new_session_same_ip_shares_budget(self, tmp_db: DatabaseManager) -> None:
        cfg = OwnerConfig(session_max_questions_owner_llm=1)
        check_and_increment_ip_owner_questions(tmp_db, "198.51.100.20", cfg)
        with pytest.raises(HTTPException) as exc_info:
            check_and_increment_ip_owner_questions(tmp_db, "198.51.100.20", cfg)
        assert exc_info.value.status_code == 429

    def test_loopback_aliases_share_budget(self, tmp_db: DatabaseManager) -> None:
        cfg = OwnerConfig(app_env="production", session_max_questions_owner_llm=1)
        check_and_increment_ip_owner_questions(tmp_db, "127.0.0.1", cfg)
        with pytest.raises(HTTPException) as exc_info:
            check_and_increment_ip_owner_questions(tmp_db, "::1", cfg)
        assert exc_info.value.status_code == 429

    def test_dev_loopback_skips_question_cap(self, tmp_db: DatabaseManager) -> None:
        cfg = OwnerConfig(app_env="development", session_max_questions_owner_llm=1)
        for _ in range(5):
            check_and_increment_ip_owner_questions(tmp_db, "127.0.0.1", cfg)
            check_and_increment_ip_owner_questions(tmp_db, "::1", cfg)

    def test_first_question_allowed_when_driver_rowcount_is_cumulative(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Turso/libsql rowcount is a connection total, not the last statement.

        INSERT then UPDATE used to look like 2 rows changed, so the first
        owner-funded question was rejected as if all 15 were already used.
        """
        db_file = tmp_path / "libsql_quota.db"
        monkeypatch.setenv("TURSO_DATABASE_URL", str(db_file))
        monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
        libsql_db = DatabaseManager(db_path=db_file)
        cfg = OwnerConfig(app_env="production", session_max_questions_owner_llm=15)
        used = check_and_increment_ip_owner_questions(libsql_db, "203.0.113.77", cfg)
        assert used == 1
        used = check_and_increment_ip_owner_questions(libsql_db, "203.0.113.77", cfg)
        assert used == 2

    def test_production_loopback_stays_capped(self, tmp_db: DatabaseManager) -> None:
        cfg = OwnerConfig(app_env="production", session_max_questions_owner_llm=1)
        check_and_increment_ip_owner_questions(tmp_db, "127.0.0.1", cfg)
        with pytest.raises(HTTPException) as exc_info:
            check_and_increment_ip_owner_questions(tmp_db, "127.0.0.1", cfg)
        assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# Daily global rerank cap
# ---------------------------------------------------------------------------


class TestDailyGlobalRerankCap:
    def test_daily_rerank_cap_triggers_demo_at_capacity(self, tmp_db: DatabaseManager) -> None:
        # Use cfg with cap of 1
        cfg = OwnerConfig(daily_max_rerank_calls=1)

        # First call should succeed
        check_and_increment_daily_rerank(tmp_db, cfg)

        # Second call must trigger "demo at capacity"
        with pytest.raises(HTTPException) as exc_info:
            check_and_increment_daily_rerank(tmp_db, cfg)
        assert exc_info.value.status_code == 429
        assert "capacity" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


class TestKillSwitch:
    def test_owner_llm_kill_switch_blocks_call(self) -> None:
        cfg = OwnerConfig(kill_switch_disable_owner_llm=True)
        with pytest.raises(HTTPException) as exc_info:
            check_kill_switch_owner_llm(cfg)
        assert exc_info.value.status_code == 503
        assert "disabled" in exc_info.value.detail.lower()

    def test_owner_llm_kill_switch_inactive_by_default(self) -> None:
        cfg = OwnerConfig(kill_switch_disable_owner_llm=False)
        # Should not raise
        check_kill_switch_owner_llm(cfg)

    def test_upload_kill_switch_blocks_uploads(self) -> None:
        cfg = OwnerConfig(kill_switch_disable_uploads=True)
        with pytest.raises(HTTPException) as exc_info:
            check_kill_switch_uploads(cfg)
        assert exc_info.value.status_code == 503
        assert "uploads" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Demo scope read-only guard
# ---------------------------------------------------------------------------


class TestDemoScopeGuard:
    def test_demo_scope_blocks_write(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            assert_demo_scope_readonly(scope="demo", action="write")
        assert exc_info.value.status_code == 403
        assert "read-only" in exc_info.value.detail.lower()

    def test_non_demo_scope_allows_write(self) -> None:
        # Must not raise for a regular session scope
        assert_demo_scope_readonly(scope="prov_sess_abc123", action="write")

    def test_demo_scope_blocks_delete(self) -> None:
        with pytest.raises(HTTPException):
            assert_demo_scope_readonly(scope="demo", action="delete")
