"""Unit tests for Privacy-Safe Tracing Engine (Phase 7 - P7-T6).

Verifies the core architectural invariant:
- Full content captured ONLY for demo corpus or explicit eval mode.
- Strict metadata-only logging for visitor uploaded documents (scope != 'demo'):
  * Zero question text, zero document content, zero answers.
- API keys are NEVER logged or retained in spans under any circumstance.
"""

from __future__ import annotations

from src.security.tracing import PrivacyLevel, TraceManager, trace_span


def test_tracing_demo_scope_allows_content() -> None:
    """Demo scope allows full content for debugging and developer visibility."""
    TraceManager.clear()

    with trace_span("demo_query", scope="demo") as span:
        span.set_attribute("question", "What is the primary purpose stated in the Preamble?")
        span.set_attribute("answer", "In order to form a more perfect Union...")
        span.set_attribute("doc_count", 2)

    assert span.privacy_level == PrivacyLevel.FULL_CONTENT
    assert span.attributes["question"] == "What is the primary purpose stated in the Preamble?"
    assert span.attributes["answer"] == "In order to form a more perfect Union..."
    assert span.attributes["doc_count"] == 2
    assert span.duration_ms >= 0.0


def test_tracing_visitor_scope_masks_all_text_content() -> None:
    """Visitor uploaded scope (scope != 'demo') strictly sanitizes all text payloads to length/counts only."""
    TraceManager.clear()
    visitor_session_id = "sess_user_priv_98765"

    with trace_span("visitor_chat", scope=visitor_session_id) as span:
        # Attempt to log sensitive visitor texts
        span.set_attribute("question", "Confidential medical record query for patient John Doe")
        span.set_attribute("prompt", "Analyze patient medical history confidential...")
        span.set_attribute("answer", "The patient diagnosis contains confidential details...")
        span.set_attribute("document_content", "Lab report results: Blood pressure 120/80...")
        span.set_attribute("candidate_count", 5)
        span.set_attribute("rerank_score", 0.94)

    assert span.privacy_level == PrivacyLevel.METADATA_ONLY

    # Ensure sensitive raw text keys are completely absent from span attributes
    for forbidden in ["question", "prompt", "answer", "document_content"]:
        assert forbidden not in span.attributes, (
            f"Forbidden sensitive key '{forbidden}' leaked in span!"
        )

    # Ensure metadata replacements exist instead
    assert "question_char_count" in span.attributes
    assert span.attributes["question_char_count"] > 0
    assert "document_content_char_count" in span.attributes
    assert span.attributes["candidate_count"] == 5
    assert span.attributes["rerank_score"] == 0.94


def test_tracing_redacts_api_keys_in_all_modes() -> None:
    """API keys are strictly redacted even in full_content / demo mode."""
    TraceManager.clear()
    fake_key = "sk-1234567890abcdef1234567890abcdef"

    with trace_span("key_test_span", scope="demo") as span:
        span.set_attribute("header_val", f"Bearer {fake_key}")
        span.set_attribute("note", f"Failed key: {fake_key}")

    assert fake_key not in span.attributes["header_val"]
    assert fake_key not in span.attributes["note"]
    assert (
        "[REDACTED_API_KEY]" in span.attributes["header_val"]
        or "[REDACTED" in span.attributes["header_val"]
    )


def test_tracing_nested_spans() -> None:
    """Nested spans properly track parent-child relationships."""
    TraceManager.clear()

    with trace_span("parent_stage", scope="demo") as parent:
        with trace_span("child_stage_1", scope="demo") as child_1:
            child_1.set_attribute("sub_step", 1)
        with trace_span("child_stage_2", scope="demo") as child_2:
            child_2.set_attribute("sub_step", 2)

    assert len(parent.child_spans) == 2
    assert parent.child_spans[0].name == "child_stage_1"
    assert parent.child_spans[1].name == "child_stage_2"
    assert parent.child_spans[0].parent_span_id == parent.span_id
