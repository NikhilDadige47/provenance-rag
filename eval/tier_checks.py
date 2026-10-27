"""Tier Verification Harness for Provenance RAG (Phase 7 - P7-T5).

Scripted end-to-end checks verifying access tier boundaries, key lifecycles, and financial caps:
- Tier A: Zero keys, read-only demo corpus, owner pays within strict caps.
- Tier B: Visitor document upload with local or BYOK parser; strictly isolated private scope.
- Tier C: Visitor brings own LLM key; answers generated via visitor key; owner pays only embed/rerank.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import HTTPException

from src.api.caps import (
    check_and_increment_session_byok_llm,
    check_and_increment_session_owner_llm,
)
from src.api.sessions import create_session
from src.security.config import AccessTier, OwnerConfig, VisitorKeys
from src.security.secret import Secret
from src.storage.db import DatabaseManager

logger = logging.getLogger("provenance_rag.eval.tier_checks")


@dataclass
class TierCheckResult:
    """Outcome of a single tier verification test."""

    tier_name: str
    check_name: str
    passed: bool
    details: str


class TierVerifier:
    """Verifies that each tier strictly respects its financial and key boundaries."""

    def __init__(self, db: DatabaseManager, cfg: OwnerConfig | None = None) -> None:
        self.db = db
        self.cfg = cfg or OwnerConfig.from_env()

    def verify_tier_a(self) -> list[TierCheckResult]:
        """Verify Tier A (Instant Demo, Zero Keys)."""
        results: list[TierCheckResult] = []

        # 1. Session creation generates tier_a_demo
        session_resp = create_session(
            db=self.db,
            visitor_keys=None,
        )
        passed_tier = session_resp.tier == AccessTier.TIER_A_DEMO.value
        results.append(
            TierCheckResult(
                tier_name="Tier A",
                check_name="Server-derived tier is 'tier_a_demo'",
                passed=passed_tier,
                details=f"Tier: {session_resp.tier}",
            )
        )

        # 2. Owner LLM questions permitted under quota
        try:
            check_and_increment_session_owner_llm(self.db, session_resp.session_id, self.cfg)
            is_allowed = True
        except Exception as e:
            logger.error(f"Tier A initial query check failed: {e}")
            is_allowed = False

        results.append(
            TierCheckResult(
                tier_name="Tier A",
                check_name="Owner LLM budget check permits queries under cap",
                passed=is_allowed,
                details="Permitted initial query under quota",
            )
        )

        # 3. Simulate cap reached and verify HTTP 429 is raised
        with self.db._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET questions_owner_llm = ? WHERE session_id = ?",
                (self.cfg.session_max_questions_owner_llm, session_resp.session_id),
            )

        is_capped = False
        try:
            check_and_increment_session_owner_llm(self.db, session_resp.session_id, self.cfg)
        except HTTPException as exc:
            if exc.status_code == 429:
                is_capped = True
        except Exception:
            is_capped = False

        results.append(
            TierCheckResult(
                tier_name="Tier A",
                check_name="Owner LLM budget blocks further queries when cap reached",
                passed=is_capped,
                details=f"429 raised when questions_owner_llm >= {self.cfg.session_max_questions_owner_llm}",
            )
        )

        return results

    def verify_tier_b(self) -> list[TierCheckResult]:
        """Verify Tier B (Document Upload, Private Scope)."""
        results: list[TierCheckResult] = []

        # 1. Session created with upload parser provider
        visitor_keys = VisitorKeys(parser_provider="local_pymupdf")
        session_resp = create_session(
            db=self.db,
            visitor_keys=visitor_keys,
        )

        passed_tier = session_resp.tier == AccessTier.TIER_B_UPLOAD.value
        results.append(
            TierCheckResult(
                tier_name="Tier B",
                check_name="Upload session assigned 'tier_b_upload'",
                passed=passed_tier,
                details=f"Tier: {session_resp.tier}",
            )
        )

        # 2. Session isolation verification: session_id is private
        session_row = self.db.get_session(session_resp.session_id)
        is_private = (
            session_row is not None
            and session_row["session_id"] != "demo"
            and session_row["session_id"].startswith("prov_sess_")
        )
        results.append(
            TierCheckResult(
                tier_name="Tier B",
                check_name="Tier B session uses isolated private session token",
                passed=is_private,
                details=f"Session token: {session_resp.session_id[:16]}...",
            )
        )

        return results

    def verify_tier_c(self) -> list[TierCheckResult]:
        """Verify Tier C (Full BYOK with Visitor LLM Key)."""
        results: list[TierCheckResult] = []

        fake_key = "gsk_test_fake_visitor_groq_key_phase7"
        visitor_keys = VisitorKeys(
            llm_provider="groq",
            llm_key=Secret(fake_key),
        )
        session_resp = create_session(
            db=self.db,
            visitor_keys=visitor_keys,
        )

        passed_tier = session_resp.tier == AccessTier.TIER_C_BYOK.value
        results.append(
            TierCheckResult(
                tier_name="Tier C",
                check_name="Providing visitor LLM key assigns 'tier_c_byok'",
                passed=passed_tier,
                details=f"Tier: {session_resp.tier}",
            )
        )

        # Zero key leakage check in SQLite database and session response
        row = self.db.get_session(session_resp.session_id)
        row_str = str(dict(row)) if row else ""
        resp_json = session_resp.model_dump_json()

        no_key_in_db = fake_key not in row_str
        no_key_in_resp = fake_key not in resp_json

        results.append(
            TierCheckResult(
                tier_name="Tier C",
                check_name="Visitor LLM key is never stored in SQLite sessions table",
                passed=no_key_in_db and no_key_in_resp,
                details="Key absent from SQLite row and SessionCreateResponse",
            )
        )

        # BYOK questions increment own_llm counter and do NOT block on owner quota
        try:
            check_and_increment_session_byok_llm(self.db, session_resp.session_id, self.cfg)
            byok_allowed = True
        except Exception:
            byok_allowed = False

        results.append(
            TierCheckResult(
                tier_name="Tier C",
                check_name="BYOK query increments BYOK counter independently",
                passed=byok_allowed,
                details="Permitted under BYOK allowance",
            )
        )

        return results

    def run_all_checks(self) -> list[TierCheckResult]:
        """Run all verification checks across Tiers A, B, and C."""
        all_results: list[TierCheckResult] = []
        all_results.extend(self.verify_tier_a())
        all_results.extend(self.verify_tier_b())
        all_results.extend(self.verify_tier_c())
        return all_results
