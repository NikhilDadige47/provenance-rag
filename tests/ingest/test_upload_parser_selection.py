"""Owner-paid upload parser selection (auto waterfall vs explicit parser)."""

from __future__ import annotations

import pytest

from src.ingest.parsers.selection import (
    DEFAULT_UPLOAD_PARSER,
    UploadParserError,
    canonical_parser_label,
    normalize_upload_parser,
    owner_parser_key,
    visitor_parser_key_required,
)
from src.security.config import OwnerConfig
from src.security.secret import Secret


def test_normalize_auto_aliases() -> None:
    assert normalize_upload_parser(None) == "auto"
    assert normalize_upload_parser("") == "auto"
    assert normalize_upload_parser("AUTO") == "auto"
    assert normalize_upload_parser("smart") == "auto"
    assert DEFAULT_UPLOAD_PARSER == "auto"


def test_normalize_local_and_cloud() -> None:
    assert normalize_upload_parser("local") == "local_pymupdf"
    assert normalize_upload_parser("landingai") == "landingai"
    assert normalize_upload_parser("llamaparse") == "llamaparse"


def test_normalize_rejects_unknown() -> None:
    with pytest.raises(UploadParserError, match="Unknown parser"):
        normalize_upload_parser("unstructured")


def test_auto_never_requires_visitor_key() -> None:
    cfg = OwnerConfig.model_construct(landingai_api_key=None, llamaparse_api_key=None)
    assert visitor_parser_key_required("auto", cfg) is False
    assert visitor_parser_key_required("local_pymupdf", cfg) is False


def test_explicit_cloud_requires_visitor_key_without_owner_pool() -> None:
    cfg = OwnerConfig.model_construct(landingai_api_key=None, llamaparse_api_key=None)
    assert visitor_parser_key_required("landingai", cfg) is True
    assert visitor_parser_key_required("llamaparse", cfg) is True


def test_explicit_cloud_uses_owner_key_when_present() -> None:
    cfg = OwnerConfig.model_construct(
        landingai_api_key=Secret("land_live_test"),
        llamaparse_api_key=Secret("llx_live_test"),
    )
    assert visitor_parser_key_required("landingai", cfg) is False
    assert visitor_parser_key_required("llamaparse", cfg) is False
    assert owner_parser_key("landingai", cfg) is not None
    assert owner_parser_key("llamaparse", cfg) is not None


def test_placeholder_owner_keys_are_ignored() -> None:
    cfg = OwnerConfig.model_construct(
        landingai_api_key=Secret("placeholder"),
        llamaparse_api_key=Secret(""),
    )
    assert owner_parser_key("landingai", cfg) is None
    assert owner_parser_key("llamaparse", cfg) is None
    assert visitor_parser_key_required("landingai", cfg) is True


def test_canonical_parser_label() -> None:
    assert canonical_parser_label("local_pymupdf:floor") == "local_pymupdf"
    assert canonical_parser_label("landingai") == "landingai"
    assert canonical_parser_label("llamaparse") == "llamaparse"
    assert canonical_parser_label(None) == "local_pymupdf"
