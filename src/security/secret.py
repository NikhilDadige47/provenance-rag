"""Secure wrapper for sensitive strings (API keys, tokens, credentials).

Guarantees that credentials cannot be accidentally printed to logs, console,
error stack traces, or serialized into JSON payloads.
"""

from __future__ import annotations

from typing import Any

from pydantic_core import CoreSchema, core_schema


class Secret:
    """Wrapper that prevents sensitive strings from leaking into logs or serialization.

    The wrapped value is completely masked in __str__, __repr__, and JSON outputs.
    The real string is only accessible via explicit .reveal().
    """

    __slots__ = ("_value",)

    def __init__(self, value: str | Secret) -> None:
        if isinstance(value, Secret):
            self._value = value._value
        elif isinstance(value, str):
            self._value = value
        else:
            raise TypeError(f"Secret must be initialized with str or Secret, got {type(value).__name__}")

    def reveal(self) -> str:
        """Explicitly access the underlying secret string."""
        return self._value

    def __str__(self) -> str:
        return "***"

    def __repr__(self) -> str:
        return "Secret('***')"

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Secret):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return False

    def __hash__(self) -> int:
        return hash(self._value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Any
    ) -> CoreSchema:
        """Pydantic v2 schema integration.

        Validates strings into Secret instances, and serializes them as '***'.
        """
        def validate_from_str(value: Any) -> Secret:
            if isinstance(value, Secret):
                return value
            if isinstance(value, str):
                return Secret(value)
            raise TypeError("Expected string or Secret")

        return core_schema.chain_schema(
            [
                core_schema.no_info_plain_validator_function(validate_from_str),
                core_schema.is_instance_schema(cls),
            ],
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda s: "***",
                info_arg=False,
                return_schema=core_schema.str_schema(),
            ),
        )
