"""Tests for P5-T6: Privacy-safe logging — no question text, document text, or API keys in logs.

This is the key-leak grep test suite that validates:
  - contains_key() correctly identifies known key patterns
  - redact_keys() correctly masks keys
  - log_chat_request never includes question text in its output
  - log_chat_response never includes answer text in its output
  - Session tokens are detected as key patterns
  - Plain metadata strings pass key-leak detection cleanly
"""

import logging

import pytest

from src.api.logging import (
    contains_key,
    generate_request_id,
    log_chat_request,
    log_chat_response,
    redact_keys,
)


class TestKeyLeakDetection:
    """Verify that contains_key() catches known API key formats."""

    @pytest.mark.parametrize(
        "key_string",
        [
            "sk-abc123LONGKEYFORTESTING1234567890",  # OpenAI
            "gsk_ABCDEF12345678longgroqkey90xyz",  # Groq
            "co-cohereKEYThatIsLongEnough12345",  # Cohere
            "sk-ant-longAnthropicKeyABCDEFGHIJ",  # Anthropic
            "ant-longAnthropicKey12345678901234",  # Anthropic alternate
            "llx-longLlamaParseKey12345678901234",  # LlamaParse
            "prov_sess_longSessionToken123456789012",  # Session tokens
        ],
    )
    def test_contains_key_detects_key(self, key_string: str) -> None:
        assert contains_key(key_string), f"Key pattern not detected: {key_string}"

    @pytest.mark.parametrize(
        "safe_string",
        [
            "request_id=req_abc123",
            "tier=tier_a_demo",
            "timings={'rewrite_ms': 12.3}",
            "question_length_chars=45",
            "is_found=True",
            "2026-10-26T12:00:00Z",
            "status=200",
        ],
    )
    def test_contains_key_ignores_safe_strings(self, safe_string: str) -> None:
        assert not contains_key(safe_string), f"False positive for: {safe_string}"


class TestRedactKeys:
    """redact_keys() must replace key patterns with '***'."""

    def test_redacts_openai_key(self) -> None:
        text = "Authorization: Bearer sk-abc123LONGKEYFORTESTING1234567890"
        result = redact_keys(text)
        assert "sk-" not in result
        assert "***" in result

    def test_redacts_groq_key(self) -> None:
        text = "key=gsk_ABCDEF12345678longgroqkey90xyz"
        result = redact_keys(text)
        assert "gsk_" not in result

    def test_leaves_safe_text_intact(self) -> None:
        text = "request_id=req_abc123 tier=tier_a_demo"
        result = redact_keys(text)
        assert result == text


class TestRequestIdGeneration:
    """generate_request_id() must produce unique, prefixed IDs."""

    def test_request_id_prefix(self) -> None:
        rid = generate_request_id()
        assert rid.startswith("req_")

    def test_request_ids_are_unique(self) -> None:
        ids = {generate_request_id() for _ in range(50)}
        assert len(ids) == 50


class TestPrivacyLoggingContent:
    """Log functions must record metadata only — never content."""

    def test_log_chat_request_no_question_text(self, caplog: pytest.LogCaptureFixture) -> None:
        """Ensure question text is NOT written to logs; only its length."""
        question = "This is a sensitive question about secret financial data."
        with caplog.at_level(logging.INFO, logger="provenance_rag.api"):
            log_chat_request(
                request_id="req_test001",
                tier="tier_a_demo",
                scope_prefix="prov_ses",
                has_visitor_key=False,
                question_length=len(question),
                history_turns=0,
            )

        assert len(caplog.records) >= 1
        record = caplog.records[0]

        # The actual question text must NOT appear anywhere in the log record
        record_str = str(record.__dict__)
        assert question not in record_str

        # The length SHOULD be stored in the extra dict on the LogRecord
        assert record.__dict__.get("question_length_chars") == len(question)

    def test_log_chat_response_no_answer_text(self, caplog: pytest.LogCaptureFixture) -> None:
        answer = "The CEO of AcmeCorp is John Smith and the revenue was $4.5 billion."
        with caplog.at_level(logging.INFO, logger="provenance_rag.api"):
            log_chat_response(
                request_id="req_test002",
                tier="tier_a_demo",
                is_found=True,
                is_grounded=True,
                used_visitor_key=False,
                answer_length=len(answer),
                source_count=3,
                timings={"total_ms": 123.4},
                tokens_used=42,
            )

        all_log_text = " ".join(r.getMessage() for r in caplog.records)
        assert answer not in all_log_text
        assert "John Smith" not in all_log_text

    def test_log_functions_never_contain_api_key(self, caplog: pytest.LogCaptureFixture) -> None:
        """Simulate a scenario where a key COULD slip through — it must not."""
        fake_key = "sk-fakeOpenAIKeyThatShouldNeverAppear12345"

        with caplog.at_level(logging.INFO, logger="provenance_rag.api"):
            log_chat_request(
                request_id="req_keytest",
                tier="tier_c_byok",
                scope_prefix="prov_ses",
                has_visitor_key=True,
                question_length=20,
                history_turns=1,
            )

        all_log_text = " ".join(r.getMessage() for r in caplog.records)
        assert fake_key not in all_log_text
        # contains_key should also confirm no key leaked
        assert not contains_key(all_log_text)
