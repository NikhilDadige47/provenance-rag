"""Tests for the Secret wrapper class and Pydantic integration."""

import json

import pytest
from pydantic import BaseModel

from src.security.secret import Secret


class DummyModel(BaseModel):
    name: str
    key: Secret


def test_secret_string_representation() -> None:
    raw = "sk-live-secret-key-12345"
    sec = Secret(raw)

    assert str(sec) == "***"
    assert repr(sec) == "Secret('***')"
    assert f"My key is {sec}" == "My key is ***"
    assert raw not in str(sec)
    assert raw not in repr(sec)


def test_secret_reveal() -> None:
    raw = "co-test-token-abcdef"
    sec = Secret(raw)
    assert sec.reveal() == raw


def test_secret_truthiness_and_equality() -> None:
    assert bool(Secret("valid-token")) is True
    assert bool(Secret("")) is False

    sec1 = Secret("abc")
    sec2 = Secret("abc")
    sec3 = Secret("xyz")

    assert sec1 == sec2
    assert sec1 == "abc"
    assert sec1 != sec3
    assert sec1 != "xyz"
    assert hash(sec1) == hash("abc")


def test_secret_type_validation() -> None:
    with pytest.raises(TypeError):
        Secret(12345)  # type: ignore[arg-type]


def test_secret_pydantic_serialization() -> None:
    raw = "gsk_live_secret_key_99999"
    model = DummyModel(name="test_service", key=Secret(raw))

    # Model string representation masks secret
    assert raw not in str(model)
    assert raw not in repr(model)

    # model_dump serializes Secret as "***"
    dump = model.model_dump()
    assert dump["key"] == "***"
    assert raw not in str(dump)

    # JSON serialization masks secret
    json_str = model.model_dump_json()
    assert raw not in json_str
    parsed = json.loads(json_str)
    assert parsed["key"] == "***"


def test_secret_pydantic_from_string() -> None:
    # Pydantic parses raw string into Secret
    model = DummyModel.model_validate({"name": "auto_parsed", "key": "raw_str_key"})
    assert isinstance(model.key, Secret)
    assert model.key.reveal() == "raw_str_key"
    assert str(model.key) == "***"
