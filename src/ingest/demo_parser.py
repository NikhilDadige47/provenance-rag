"""Owner-selectable parser used only for demo-corpus ingestion.

Visitor uploads still go through the credit-engineered waterfall. Demo ingest
is a one-time owner job, so DEMO_PARSER can be llamaparse/landingai/local_pymupdf
without changing Tier B behavior.
"""

from __future__ import annotations

from src.ingest.parsers.registry import default_parser_registry
from src.ingest.parsers.selection import owner_parser_key
from src.interfaces import IParser
from src.security.config import OwnerConfig
from src.security.secret import Secret

DEMO_PARSER_CHOICES = ("local_pymupdf", "llamaparse", "landingai")
DEFAULT_DEMO_PARSER = "local_pymupdf"


class DemoParserError(ValueError):
    """Invalid DEMO_PARSER name or missing owner key for a cloud parser."""


def owner_key_for_parser(name: str, cfg: OwnerConfig) -> Secret | None:
    """Return the owner env key for a demo parser, if one is required."""
    return owner_parser_key(name, cfg)


def resolve_demo_parser(
    name: str | None = None,
    cfg: OwnerConfig | None = None,
) -> tuple[IParser, Secret | None]:
    """Resolve the demo-corpus parser from an explicit name or DEMO_PARSER.

    Returns (parser, api_key). api_key is None for local_pymupdf.
    """
    config = cfg or OwnerConfig.from_env()
    chosen = (name or config.demo_parser or DEFAULT_DEMO_PARSER).strip().lower()
    if chosen not in DEMO_PARSER_CHOICES:
        raise DemoParserError(
            f"Unknown demo parser '{chosen}'. Choose one of: {', '.join(DEMO_PARSER_CHOICES)}"
        )

    parser = default_parser_registry.get(chosen)
    if not parser.requires_key:
        return parser, None

    api_key = owner_key_for_parser(chosen, config)
    if api_key is None:
        env_name = "LLAMAPARSE_API_KEY" if chosen == "llamaparse" else "LANDINGAI_API_KEY"
        raise DemoParserError(
            f"DEMO_PARSER={chosen} requires {env_name} in the owner .env. "
            "Set the key or switch DEMO_PARSER=local_pymupdf."
        )
    return parser, api_key
