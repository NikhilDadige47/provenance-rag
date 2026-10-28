"""Upload parser selection: owner-paid auto waterfall vs an explicit parser.

Visitor uploads default to ``auto``:

    1. Count pages locally (Gate 0, $0)
    2. Landing AI if the owner key exists and remaining credits cover this file
    3. LlamaParse if Landing AI cannot take it
    4. Local PyMuPDF as the infinite free floor

DEMO_PARSER (``src.ingest.demo_parser``) is independent and never used here.
"""

from __future__ import annotations

from src.security.config import OwnerConfig
from src.security.secret import Secret

UPLOAD_PARSER_CHOICES = ("auto", "landingai", "llamaparse", "local_pymupdf")
DEFAULT_UPLOAD_PARSER = "auto"
CLOUD_PARSERS = ("landingai", "llamaparse")

_AUTO_ALIASES = frozenset({"", "auto", "smart", "owner", "waterfall"})
_LOCAL_ALIASES = frozenset({"local", "pymupdf", "local_pymupdf"})


class UploadParserError(ValueError):
    """Unknown or unsupported upload parser name."""


def usable_owner_secret(secret: Secret | None) -> Secret | None:
    """Return the secret only if it is a real key, not empty or a placeholder."""
    if secret is None:
        return None
    value = secret.reveal().strip()
    if not value or "placeholder" in value.lower():
        return None
    return secret


def owner_parser_key(name: str, cfg: OwnerConfig | None) -> Secret | None:
    """Owner .env key for a named cloud parser, if one is configured."""
    if cfg is None:
        return None
    if name == "landingai":
        return usable_owner_secret(cfg.landingai_api_key)
    if name == "llamaparse":
        return usable_owner_secret(cfg.llamaparse_api_key)
    return None


def normalize_upload_parser(name: str | None) -> str:
    """Canonicalize the upload parser form field. Raises UploadParserError if unknown."""
    raw = (name or DEFAULT_UPLOAD_PARSER).strip().lower()
    if raw in _AUTO_ALIASES:
        return DEFAULT_UPLOAD_PARSER
    if raw in _LOCAL_ALIASES:
        return "local_pymupdf"
    if raw not in UPLOAD_PARSER_CHOICES:
        raise UploadParserError(
            f"Unknown parser '{name}'. Choose one of: {', '.join(UPLOAD_PARSER_CHOICES)}"
        )
    return raw


def visitor_parser_key_required(parser_name: str, cfg: OwnerConfig) -> bool:
    """True only when the visitor explicitly picked a cloud parser the owner cannot fund.

    ``auto`` never requires a visitor key: missing owner credits fall through to local PyMuPDF.
    """
    try:
        name = normalize_upload_parser(parser_name)
    except UploadParserError:
        return False
    if name in (DEFAULT_UPLOAD_PARSER, "local_pymupdf"):
        return False
    if name in CLOUD_PARSERS:
        return owner_parser_key(name, cfg) is None
    return True


def canonical_parser_label(label: str | None) -> str:
    """Collapse router labels such as ``local_pymupdf:floor`` into a stored parser name."""
    raw = (label or "local_pymupdf").strip().lower()
    if raw.startswith("landing"):
        return "landingai"
    if raw.startswith("llama"):
        return "llamaparse"
    if "pymupdf" in raw or raw in _LOCAL_ALIASES or raw in {"cache", "floor"}:
        return "local_pymupdf"
    return raw
