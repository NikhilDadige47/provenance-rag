"""Privacy-Safe Tracing and Observability Engine (Phase 7 - P7-T6).

Implements strict observability with zero visitor data leakage:
- Full content traces ONLY for scope == 'demo' or explicit dev/eval benchmarking.
- Metadata-only traces for visitor uploaded documents (scope != 'demo'):
  * Zero question text, zero document passages, zero API keys.
  * Captures only latency timings, status codes, token counts, candidate counts, and rerank scores.
"""

from __future__ import annotations

import contextvars
import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.security.redaction import redact_sensitive_str

logger = logging.getLogger("provenance_rag.security.tracing")

# Context variable for the active trace span stack
_current_trace: contextvars.ContextVar[TraceSpan | None] = contextvars.ContextVar(
    "_current_trace", default=None
)


class PrivacyLevel(StrEnum):
    """Controls the granularity of data captured in traces."""

    FULL_CONTENT = "full_content"  # For demo corpus and automated evaluation only
    METADATA_ONLY = "metadata_only"  # For visitor uploaded documents (strict GDPR/Privacy)


@dataclass
class SpanEvent:
    """A timestamped event or metric within a span."""

    name: str
    timestamp: float
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceSpan:
    """An individual span within an end-to-end request trace."""

    span_id: str
    name: str
    scope: str
    privacy_level: PrivacyLevel
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    duration_ms: float = 0.0
    status: str = "ok"
    error_message: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)
    child_spans: list[TraceSpan] = field(default_factory=list)

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute respecting the privacy policy."""
        # Never store API keys in any span regardless of privacy level
        if isinstance(value, str):
            value = redact_sensitive_str(value)

        # For visitor documents, reject text payload keys
        if self.privacy_level == PrivacyLevel.METADATA_ONLY:
            sensitive_keys = {
                "question",
                "query",
                "prompt",
                "answer",
                "text",
                "snippet",
                "passage",
                "document_content",
                "expanded_context",
            }
            if any(s in key.lower() for s in sensitive_keys):
                # Replace with non-sensitive length/count metadata
                if isinstance(value, (str, bytes)):
                    self.attributes[f"{key}_char_count"] = len(value)
                elif isinstance(value, list):
                    self.attributes[f"{key}_item_count"] = len(value)
                return

        self.attributes[key] = value

    def finish(self, status: str = "ok", error: Exception | None = None) -> None:
        """Close the span and record execution duration."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000.0
        self.status = status
        if error is not None:
            self.error_message = redact_sensitive_str(str(error))
            self.status = "error"

    def to_dict(self) -> dict[str, Any]:
        """Serialize span to dictionary for telemetry logging or export."""
        return {
            "span_id": self.span_id,
            "name": self.name,
            "scope": self.scope,
            "privacy_level": self.privacy_level.value,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "error_message": self.error_message,
            "attributes": self.attributes,
            "child_count": len(self.child_spans),
        }


class TraceManager:
    """Manages active spans and global trace collection for testing and diagnostics."""

    _collected_spans: list[TraceSpan] = []

    @classmethod
    def determine_privacy_level(cls, scope: str, is_eval: bool = False) -> PrivacyLevel:
        """Enforce strict invariant: Only demo or explicit eval can capture content."""
        if is_eval or scope == "demo":
            return PrivacyLevel.FULL_CONTENT
        return PrivacyLevel.METADATA_ONLY

    @classmethod
    def record_span(cls, span: TraceSpan) -> None:
        """Store span in collector."""
        cls._collected_spans.append(span)

    @classmethod
    def get_collected_spans(cls) -> list[TraceSpan]:
        """Return all collected spans."""
        return list(cls._collected_spans)

    @classmethod
    def clear(cls) -> None:
        """Clear collector."""
        cls._collected_spans.clear()


@contextmanager
def trace_span(
    name: str,
    scope: str = "unknown",
    is_eval: bool = False,
    attributes: dict[str, Any] | None = None,
) -> Generator[TraceSpan, None, None]:
    """Context manager for tracing execution stages with automatic privacy enforcement.

    Usage:
        with trace_span("hybrid_search", scope=session_id) as span:
            span.set_attribute("limit", 10)
            ...
    """
    import uuid

    privacy_level = TraceManager.determine_privacy_level(scope=scope, is_eval=is_eval)
    parent = _current_trace.get()
    parent_id = parent.span_id if parent else None

    span = TraceSpan(
        span_id=f"span_{uuid.uuid4().hex[:10]}",
        name=name,
        scope=scope,
        privacy_level=privacy_level,
        parent_span_id=parent_id,
    )

    if attributes:
        for k, v in attributes.items():
            span.set_attribute(k, v)

    token = _current_trace.set(span)
    try:
        yield span
        span.finish(status="ok")
    except Exception as exc:
        span.finish(status="error", error=exc)
        raise
    finally:
        _current_trace.reset(token)
        if parent:
            parent.child_spans.append(span)
        TraceManager.record_span(span)
        logger.debug(
            f"Span completed: {span.name} [{span.scope}] in {span.duration_ms:.1f}ms (level={span.privacy_level.value})"
        )
