"""Security audit tests: Verifies that no API key or token leaks into logs, exceptions, or payloads."""

import io
import logging

import pytest

from src.api.connections import ConnectionTestResponse
from src.security.config import OwnerConfig, VisitorKeys
from src.security.errors import (
    InvalidKeyError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.security.redaction import RedactionFilter, redact_dict, redact_text
from src.security.secret import Secret


@pytest.mark.asyncio
async def test_end_to_end_key_leakage() -> None:
    fake_visitor_parser_key = "llx-secret-visitor-parser-key-XYZ12345"
    fake_visitor_llm_key = "gsk_secret_visitor_llm_key_ABC98765"
    fake_owner_cohere_key = "co-secret-owner-cohere-key-DEF55555"

    all_raw_secrets = [
        fake_visitor_parser_key,
        fake_visitor_llm_key,
        fake_owner_cohere_key,
    ]

    captured_outputs: list[str] = []

    # 1. Test Secret string/repr/dump
    sec_p = Secret(fake_visitor_parser_key)
    sec_l = Secret(fake_visitor_llm_key)
    sec_o = Secret(fake_owner_cohere_key)

    captured_outputs.append(str(sec_p))
    captured_outputs.append(repr(sec_p))
    captured_outputs.append(str(sec_l))
    captured_outputs.append(str(sec_o))

    # 2. Test VisitorKeys model
    v_keys = VisitorKeys(
        parser_provider="llamaparse",
        parser_key=sec_p,
        llm_provider="groq",
        llm_key=sec_l,
    )
    captured_outputs.append(str(v_keys))
    captured_outputs.append(repr(v_keys))
    captured_outputs.append(v_keys.model_dump_json())

    # 3. Test OwnerConfig model
    o_config = OwnerConfig(
        cohere_api_key=sec_o,
        default_llm_api_key=sec_l,
    )
    captured_outputs.append(str(o_config))
    captured_outputs.append(repr(o_config))
    captured_outputs.append(o_config.model_dump_json())

    # 4. Test Exceptions
    err1 = InvalidKeyError("llamaparse", is_visitor_key=True)
    err2 = QuotaExhaustedError("groq", is_visitor_key=True)
    err3 = RateLimitedError("cohere", is_visitor_key=False)

    captured_outputs.extend([str(err1), repr(err1), str(err2), repr(err2), str(err3), repr(err3)])

    # 5. Test Logging handler with filter
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.addFilter(RedactionFilter())
    logger = logging.getLogger("leakage_test_logger")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    logger.info(f"Visitor initialized parser with key: {sec_p}")
    logger.warning(f"Error calling Cohere with key: {sec_o}")
    logger.error("Raw token string sk-1234567890abcdef123456 passed in request")

    captured_outputs.append(log_stream.getvalue())

    # 6. Test Dictionary and text redaction
    sample_dict = {
        "user_keys": {
            "parser_key": fake_visitor_parser_key,
            "llm_key": fake_visitor_llm_key,
        },
        "query": f"Why is my key {fake_visitor_parser_key} failing?",
    }
    redacted_d = redact_dict(sample_dict)
    captured_outputs.append(str(redacted_d))

    redacted_t = redact_text(f"Auth token was Bearer {fake_visitor_llm_key}")
    captured_outputs.append(redacted_t)

    # 7. Test Connection Test Response
    conn_resp = ConnectionTestResponse(
        ok=False,
        provider="groq",
        error=err2.message,
        hint="Contact support with error details",
    )
    captured_outputs.append(conn_resp.model_dump_json())

    # COMBINED AUDIT: Verify that none of the raw secrets ever appear in any captured output!
    all_text = "\n".join(captured_outputs)
    for raw_secret in all_raw_secrets:
        assert raw_secret not in all_text, (
            f"CRITICAL SECURITY LEAK: Raw secret '{raw_secret}' was found in outputs!"
        )
