"""Owner LLM token reservation and real usage commit."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from src.generation.llm import TokenUsage
from src.security.config import OwnerConfig
from src.security.credit_config import DAILY_GLOBAL, VISITOR_ALLOWANCE, today_str
from src.security.ledger import Ledger
from src.security.token_meter import (
    commit_owner_llm_tokens,
    estimate_generation_reserve,
    reserve_owner_llm_tokens,
)
from src.storage.db import DatabaseManager


def test_owner_config_defaults_come_from_credit_config() -> None:
    fields = OwnerConfig.model_fields
    assert (
        fields["session_max_questions_owner_llm"].default
        == VISITOR_ALLOWANCE["session_max_questions_owner_llm"]
    )
    assert fields["session_max_documents"].default == VISITOR_ALLOWANCE["session_max_documents"]
    assert fields["session_max_total_pages"].default == VISITOR_ALLOWANCE["max_pages_doc"]
    assert fields["daily_max_owner_llm_tokens"].default == DAILY_GLOBAL["max_owner_llm_tokens"]


def test_estimate_generation_reserve_includes_output_cap() -> None:
    reserved = estimate_generation_reserve("hello world " * 20)
    assert reserved > 1024


@pytest.mark.asyncio
async def test_reserve_owner_llm_tokens_rejects_when_daily_cap_hit(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "token_meter.db")
    ledger = Ledger(db.db_path)
    cfg = OwnerConfig(daily_max_owner_llm_tokens=10)
    await reserve_owner_llm_tokens(ledger, "sess1", "127.0.0.1", 10, cfg)
    with pytest.raises(HTTPException) as exc:
        await reserve_owner_llm_tokens(ledger, "sess1", "127.0.0.1", 1, cfg)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_commit_reconciles_actual_prompt_and_completion(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "token_commit.db")
    ledger = Ledger(db.db_path)
    cfg = OwnerConfig(daily_max_owner_llm_tokens=5000)
    buckets = await reserve_owner_llm_tokens(ledger, "sess2", "10.0.0.2", 1500, cfg)
    usage = TokenUsage(prompt_tokens=800, completion_tokens=200)
    actual = await commit_owner_llm_tokens(
        ledger, buckets, usage, db, cfg, session_id="sess2"
    )
    assert actual == 1000
    assert ledger.get_balance(f"day:owner_llm:{today_str()}") == 1000
    daily = db.get_daily_usage(today_str())
    assert daily["owner_llm_tokens"] == 1000
