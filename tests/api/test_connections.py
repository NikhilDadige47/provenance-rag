"""Unit tests for API key verification models, schemas, and helpers."""

from src.api.connections import PROVIDER_PROBE_URLS, ConnectionTestResponse
from src.api.main import ConnectionTestBody, PublicConfigResponse


class TestConnectionDataModels:
    def test_provider_urls_configured(self):
        required = {"groq", "openai", "anthropic", "gemini", "mistral", "cohere", "llamaparse"}
        for provider in required:
            assert provider in PROVIDER_PROBE_URLS
            assert PROVIDER_PROBE_URLS[provider].startswith("https://")

    def test_response_serialization_success(self):
        res = ConnectionTestResponse(
            ok=True,
            provider="groq",
            models=["llama-3.3-70b-versatile"],
        )
        data = res.model_dump()
        assert data["ok"] is True
        assert data["provider"] == "groq"
        assert data["models"] == ["llama-3.3-70b-versatile"]
        assert data["error"] is None

    def test_response_serialization_failure(self):
        res = ConnectionTestResponse(
            ok=False,
            provider="anthropic",
            error="Your anthropic API key was rejected as invalid or unauthorized.",
            hint="Please check provider console.",
        )
        data = res.model_dump()
        assert data["ok"] is False
        assert data["provider"] == "anthropic"
        assert "rejected as invalid" in data["error"]

    def test_body_schema_accepts_clean_fields(self):
        body = ConnectionTestBody(provider="groq", key="gsk_12345", base_url=None)
        assert body.provider == "groq"
        assert body.key == "gsk_12345"
        assert body.base_url is None

    def test_body_schema_defaults(self):
        body = ConnectionTestBody(provider="ollama")
        assert body.provider == "ollama"
        assert body.key == ""
        assert body.base_url is None

    def test_public_config_response(self):
        config = PublicConfigResponse(
            default_llm_provider="groq",
            default_llm_model="openai/gpt-oss-120b",
            demo_parser="llamaparse",
            session_ttl_hours=2.0,
        )
        assert config.default_llm_provider == "groq"
        assert config.default_llm_model == "openai/gpt-oss-120b"
        data = config.model_dump()
        assert data["default_llm_model"] == "openai/gpt-oss-120b"
