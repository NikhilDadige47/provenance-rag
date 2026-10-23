"""Tests for redaction of text, dictionaries, and Python logging."""

import io
import logging

from src.security.redaction import RedactionFilter, redact_dict, redact_text


def test_redact_bearer_token() -> None:
    text = "Authorization: Bearer secret_token_1234567890"
    cleaned = redact_text(text)
    assert "secret_token_1234567890" not in cleaned
    assert "Authorization: Bearer [REDACTED]" in cleaned


def test_redact_known_key_prefixes() -> None:
    text = (
        "Connecting with sk-1234567890abcdef123456 and co-abcdef1234567890123456 "
        "and gsk_1234567890abcdef123456"
    )
    cleaned = redact_text(text)
    assert "sk-1234567890abcdef123456" not in cleaned
    assert "co-abcdef1234567890123456" not in cleaned
    assert "gsk_1234567890abcdef123456" not in cleaned
    assert "[REDACTED_OPENAI_KEY]" in cleaned
    assert "[REDACTED_COHERE_KEY]" in cleaned
    assert "[REDACTED_GROQ_KEY]" in cleaned


def test_redact_url_parameters() -> None:
    url = "https://example.com/api?api_key=my_super_secret_key&limit=10"
    cleaned = redact_text(url)
    assert "my_super_secret_key" not in cleaned
    assert "api_key=[REDACTED]" in cleaned
    assert "limit=10" in cleaned


def test_redact_headers() -> None:
    header = "x-parser-key: llx_live_parser_token_9999"
    cleaned = redact_text(header)
    assert "llx_live_parser_token_9999" not in cleaned
    assert "x-parser-key: [REDACTED]" in cleaned


def test_redact_dict_recursive() -> None:
    data = {
        "status": "ok",
        "api_key": "raw_secret_value",
        "parser_key": "parser_secret_123",
        "nested": {
            "token": "nested_secret",
            "safe_field": "safe_value",
            "message": "User with sk-1234567890abcdef123456 called endpoint",
        },
        "items": [
            {"password": "pass123"},
            "Bear text: Bearer token_987654321",
        ],
    }

    cleaned = redact_dict(data)

    assert cleaned["api_key"] == "***"
    assert cleaned["parser_key"] == "***"
    assert cleaned["nested"]["token"] == "***"
    assert cleaned["nested"]["safe_field"] == "safe_value"
    assert "sk-1234567890abcdef123456" not in cleaned["nested"]["message"]
    assert cleaned["items"][0]["password"] == "***"
    assert "token_987654321" not in cleaned["items"][1]


def test_logging_redaction_filter() -> None:
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.addFilter(RedactionFilter())

    logger = logging.getLogger("test_redaction_logger")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    secret_key = "sk-1234567890abcdef123456"
    logger.info("Service initialized with key: %s", secret_key)
    logger.warning("Failed call with Bearer secret_bearer_token_1234")

    output = log_stream.getvalue()
    assert secret_key not in output
    assert "secret_bearer_token_1234" not in output
    assert "[REDACTED_OPENAI_KEY]" in output
    assert "Bearer [REDACTED]" in output
