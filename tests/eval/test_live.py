"""Live-eval guards: demo index is semantic-only; Cohere key detection."""

from eval.live import LiveIndexError, ensure_semantic_live_config, has_usable_cohere_key
from eval.strategies import LIVE_ABLATION_CONFIGS, config_by_name
from src.security.config import OwnerConfig
from src.security.secret import Secret


def test_live_ablation_skips_simple_chunking() -> None:
    names = [cfg.name for cfg in LIVE_ABLATION_CONFIGS]
    assert "1_simple_chunking" not in names
    assert names == ["2_semantic_chunking", "3_hybrid_search", "4_reranking"]


def test_ensure_semantic_live_config_rejects_simple() -> None:
    try:
        ensure_semantic_live_config(config_by_name("1_simple_chunking"))
    except LiveIndexError as exc:
        assert "Simple chunking" in str(exc)
    else:
        raise AssertionError("expected LiveIndexError for simple chunking")
    ensure_semantic_live_config(config_by_name("4_reranking"))


def test_has_usable_cohere_key_rejects_placeholder() -> None:
    placeholder = OwnerConfig.model_construct(cohere_api_key=Secret("co_placeholder"))
    empty = OwnerConfig.model_construct(cohere_api_key=Secret(""))
    real = OwnerConfig.model_construct(cohere_api_key=Secret("real-cohere-key-abc"))
    assert has_usable_cohere_key(placeholder) is False
    assert has_usable_cohere_key(empty) is False
    assert has_usable_cohere_key(real) is True
