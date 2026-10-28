"""Demo-corpus parser selection is independent of visitor upload parsing."""

import pytest

from src.ingest.demo_parser import DemoParserError, resolve_demo_parser
from src.security.config import OwnerConfig
from src.security.secret import Secret


def test_default_demo_parser_is_local_pymupdf() -> None:
    cfg = OwnerConfig.model_construct(demo_parser="local_pymupdf")
    parser, key = resolve_demo_parser(cfg=cfg)
    assert parser.name == "local_pymupdf"
    assert parser.requires_key is False
    assert key is None


def test_resolve_llamaparse_uses_owner_key() -> None:
    cfg = OwnerConfig.model_construct(
        demo_parser="llamaparse",
        llamaparse_api_key=Secret("llx-owner-demo-key"),
    )
    parser, key = resolve_demo_parser(cfg=cfg)
    assert parser.name == "llamaparse"
    assert key is not None
    assert key.reveal() == "llx-owner-demo-key"


def test_explicit_name_overrides_env() -> None:
    cfg = OwnerConfig.model_construct(
        demo_parser="llamaparse",
        llamaparse_api_key=Secret("llx-owner-demo-key"),
    )
    parser, key = resolve_demo_parser(name="local_pymupdf", cfg=cfg)
    assert parser.name == "local_pymupdf"
    assert key is None


def test_llamaparse_without_key_fails_loudly() -> None:
    cfg = OwnerConfig.model_construct(demo_parser="llamaparse", llamaparse_api_key=None)
    with pytest.raises(DemoParserError, match="LLAMAPARSE_API_KEY"):
        resolve_demo_parser(cfg=cfg)


def test_unknown_demo_parser_rejected() -> None:
    cfg = OwnerConfig.model_construct(demo_parser="not-a-parser")
    with pytest.raises(DemoParserError, match="Unknown demo parser"):
        resolve_demo_parser(cfg=cfg)
