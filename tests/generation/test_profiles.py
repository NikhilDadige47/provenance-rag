"""Tests for model capabilities registry and dynamic prompt profiles."""

from src.generation.profiles import (
    ModelProfile,
    ModelTier,
    get_model_profile,
)
from src.generation.prompt import build_generation_prompt
from src.retrieval.expansion import ExpandedContextPassage


def _make_sample_passage(idx: int = 1) -> ExpandedContextPassage:
    return ExpandedContextPassage(
        passage_id=f"p{idx}",
        doc_id="doc1",
        title="Security Architecture",
        breadcrumb="Section 4 > Encryption",
        page=4,
        text="Data at rest is encrypted using AES-256-GCM. Keys are rotated every 90 days.",
        token_count=18,
        is_parent_expanded=True,
        source_chunk_ids=[f"c{idx}"],
    )


def test_model_tier_resolution_micro():
    """Verify micro models (<= 3B) resolve to MICRO tier with 2 chunks max."""
    models = ["qwen2.5:1.5b", "llama3.2:1b", "llama3.2:3b", "phi3:mini", "tinyllama"]
    for m in models:
        profile = get_model_profile(m)
        assert profile.tier == ModelTier.MICRO, f"Failed for {m}"
        assert profile.max_context_chunks == 2
        assert profile.temperature <= 0.1


def test_model_tier_resolution_mid():
    """Verify mid-sized models (7B - 14B) resolve to MID tier with 3 chunks max."""
    models = ["llama3.1:8b", "mistral:7b", "qwen2.5:14b", "gemma2:9b"]
    for m in models:
        profile = get_model_profile(m)
        assert profile.tier == ModelTier.MID, f"Failed for {m}"
        assert profile.max_context_chunks == 3


def test_model_tier_resolution_frontier():
    """Verify high-capacity and cloud models resolve to FRONTIER tier with 5 chunks max."""
    models = ["llama-3.3-70b-versatile", "gpt-4o", "claude-3-5-sonnet", None]
    for m in models:
        profile = get_model_profile(m)
        assert profile.tier == ModelTier.FRONTIER, f"Failed for {m}"
        assert profile.max_context_chunks == 5


def test_micro_prompt_includes_one_shot_example():
    """Verify micro profile prompt embeds a 1-shot demonstration for grounding."""
    passages = [_make_sample_passage(1)]
    profile = get_model_profile("qwen2.5:1.5b")
    sys_prompt, user_prompt = profile.build_prompts("How is data encrypted?", passages)

    assert "EXAMPLE CITATION FORMAT:" in user_prompt
    assert "AES-256" in user_prompt
    assert "[1]" in user_prompt
    assert "How is data encrypted?" in user_prompt
    assert "RULES:" in sys_prompt


def test_build_generation_prompt_backward_compatibility():
    """Verify build_generation_prompt works with and without explicit profile."""
    passages = [_make_sample_passage(1)]

    # Without profile -> backward compatible
    sys1, user1 = build_generation_prompt("Test question?", passages)
    assert "UNTRUSTED REFERENCE CONTEXT" in user1
    assert "GROUNDING RULES" in sys1

    # With micro profile
    micro_prof = get_model_profile("llama3.2:1b")
    sys2, user2 = build_generation_prompt("Test question?", passages, profile=micro_prof)
    assert "EXAMPLE CITATION FORMAT:" in user2
