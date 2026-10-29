"""Multi-provider Fallback Router and Credit-Engineered Parser Pipeline.

Implements §4, §7, and §12 of token-engineering-guide.md:
- Pre-flight estimation Gate 0 ($0 in-memory inspection)
- SHA-256 deduplication cache (instant $0 repeat parses)
- Waterfall chain: Landing AI -> LlamaParse -> Local PyMuPDF
- Multi-bucket atomic reserve -> call -> commit/release
- Circuit breaker trip on 402 Quota Exhaustion (30 min TTL)
- Guaranteed infinite free floor via local PyMuPDF
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ingest.estimator import (
    InputRejectedError,
    analyse_pdf,
    landing_route,
    landing_units,
    llama_units,
)
from src.ingest.parsers.landingai import LandingAIAdapter
from src.ingest.parsers.llamaparse import LlamaParseAdapter
from src.ingest.parsers.local_pymupdf import LocalPyMuPDFParser
from src.ingest.parsers.selection import owner_parser_key
from src.ingest.parsers.structured_doc import StructuredDoc
from src.security.breaker import Breaker
from src.security.config import OwnerConfig
from src.security.credit_config import (
    GLOBAL_PARSE_CACHE_PARSER,
    GLOBAL_PARSE_CACHE_VERSION,
    LANDING_MODELS,
    PARSE_CACHE_TTL_SECONDS,
    VISITOR_ALLOWANCE,
    cycle_str,
    daily_cap_units,
    landing_pool_key,
    today_str,
    usable_units,
    visitor_bucket_id,
)
from src.security.errors import (
    ProviderTimeoutError,
    QuotaExhaustedError,
    RateLimitedError,
)
from src.security.ledger import Bucket, Ledger
from src.security.secret import Secret
from src.storage.db import DatabaseManager

logger = logging.getLogger("provenance_rag.ingest.router")


@dataclass
class RequestContext:
    """Context holding session identity, client IP, content hash, and BYOK flags."""

    session_id: str
    client_ip: str
    sha: str
    byok: bool = False
    parser_secret: Secret | None = None


@dataclass
class ParseExecutionResult:
    """Standardized response from the multi-tier parser router."""

    structured_doc: StructuredDoc
    parser_label: str
    degraded: bool
    fallback_trail: list[tuple[str, str]] = field(default_factory=list)
    credits_charged: int = 0
    cache_hit: bool = False


class FallbackParserRouter:
    """Orchestrates multi-provider parsing with credit reservation and circuit breaking."""

    def __init__(
        self,
        db: DatabaseManager,
        ledger: Ledger | None = None,
        breaker: Breaker | None = None,
        cfg: OwnerConfig | None = None,
    ) -> None:
        self.db = db
        self.cfg = cfg or OwnerConfig.from_env()
        self.ledger = ledger or Ledger(db.db_path)
        self.breaker = breaker or Breaker(db.db_path)
        self.landing_adapter = LandingAIAdapter()
        self.llama_adapter = LlamaParseAdapter()
        self.local_adapter = LocalPyMuPDFParser()

    async def parse_with_fallback(
        self,
        pdf_path: Path,
        pdf_bytes: bytes,
        ctx: RequestContext,
        preferred_parser: str = "auto",
    ) -> ParseExecutionResult:
        """Execute pre-flight gate, cache check, and waterfall with atomic credit reservation."""
        # 1. Gate 0: Free, local PyMuPDF pre-flight inspection
        info = analyse_pdf(pdf_bytes)

        # 2. Global file-hash cache (SHA-256). Repeats across sessions cost 0.
        cached_json = self.db.get_parse_cache(
            content_hash=ctx.sha,
            parser=GLOBAL_PARSE_CACHE_PARSER,
            parser_version=GLOBAL_PARSE_CACHE_VERSION,
            max_age_seconds=PARSE_CACHE_TTL_SECONDS,
        )
        if cached_json:
            try:
                cached_data = json.loads(cached_json)
                cached_doc_payload = cached_data.get("doc") or cached_data
                s_doc = StructuredDoc(**cached_doc_payload)
                logger.info(f"Parse dedup cache HIT for {ctx.sha[:10]}: charged 0 credits")
                return ParseExecutionResult(
                    structured_doc=s_doc,
                    parser_label=cached_data.get("parser_label", s_doc.parser_used or "cache"),
                    degraded=bool(cached_data.get("degraded", False)),
                    credits_charged=0,
                    cache_hit=True,
                    fallback_trail=[("cache", "hit")],
                )
            except Exception as e:
                logger.warning(f"Error reading parse cache: {e}")

        # 3. Determine Waterfall Chain
        chain = self._build_chain(preferred_parser, ctx.byok)
        fallback_trail: list[tuple[str, str]] = []

        for provider_name, is_paid, is_degraded in chain:
            # Check if an API key exists (either owner or visitor BYOK)
            if is_paid and not self._has_key_for_provider(provider_name, ctx):
                logger.debug(f"Skipping '{provider_name}': no API key configured in .env or session")
                fallback_trail.append((provider_name, "no_key_configured"))
                continue

            # Check Circuit Breaker
            if is_paid and await self.breaker.is_open(provider_name):
                logger.info(f"Skipping '{provider_name}': circuit breaker is OPEN")
                fallback_trail.append((provider_name, "breaker_open"))
                continue

            buckets: list[Bucket] = []
            units = 0

            # Atomic Multi-Bucket Credit Reservation (Paid non-BYOK only)
            if is_paid and not ctx.byok:
                units = self._estimate_units(provider_name, info)
                buckets = self._build_buckets(provider_name, ctx, units, info)

                ok, failed_key = await self.ledger.reserve(buckets)
                if not ok:
                    logger.info(f"Skipping '{provider_name}': budget reserve failed on '{failed_key}'")
                    fallback_trail.append((provider_name, f"budget:{failed_key}"))
                    continue

            # Execute Parsing Call
            try:
                logger.info(f"Dispatching parse to '{provider_name}' (reserved={units} units)")
                structured_doc = await self._call_provider(provider_name, pdf_path, ctx, info)

                actual_units = (
                    structured_doc.credits_units
                    if structured_doc.credits_units is not None
                    else units
                )
                if buckets:
                    await self.ledger.commit(buckets, actual_units)

                try:
                    self.db.set_parse_cache(
                        content_hash=ctx.sha,
                        parser=GLOBAL_PARSE_CACHE_PARSER,
                        parser_version=GLOBAL_PARSE_CACHE_VERSION,
                        raw_result_blob=json.dumps(
                            {
                                "doc": structured_doc.model_dump(),
                                "parser_label": provider_name,
                                "degraded": is_degraded,
                            }
                        ),
                    )
                except Exception as cache_err:
                    logger.warning(f"Failed to cache parse result: {cache_err}")

                fallback_trail.append((provider_name, "ok"))
                return ParseExecutionResult(
                    structured_doc=structured_doc,
                    parser_label=provider_name,
                    degraded=is_degraded,
                    fallback_trail=fallback_trail,
                    credits_charged=actual_units if buckets else 0,
                    cache_hit=False,
                )

            except InputRejectedError:
                if buckets:
                    await self.ledger.release(buckets)
                raise

            except QuotaExhaustedError:
                if buckets:
                    await self.ledger.release(buckets)
                await self.breaker.trip_quota(provider_name, ttl_seconds=1800)
                logger.warning(f"Provider '{provider_name}' exhausted quota (402). Tripped breaker for 30m.")
                fallback_trail.append((provider_name, "quota_exhausted"))
                continue

            except (RateLimitedError, ProviderTimeoutError, Exception) as exc:
                if buckets:
                    await self.ledger.release(buckets)
                await self.breaker.record_failure(provider_name)
                logger.warning(f"Provider '{provider_name}' failed with {type(exc).__name__}: {exc}")
                fallback_trail.append((provider_name, f"transient:{type(exc).__name__}"))
                continue

        # If every lane failed, PyMuPDFLocal guarantees fallback
        logger.info("Engaging infinite floor PyMuPDFLocal parser")
        doc = await self.local_adapter.parse(pdf_path)
        fallback_trail.append(("pymupdf_floor", "ok"))
        try:
            self.db.set_parse_cache(
                content_hash=ctx.sha,
                parser=GLOBAL_PARSE_CACHE_PARSER,
                parser_version=GLOBAL_PARSE_CACHE_VERSION,
                raw_result_blob=json.dumps(
                    {
                        "doc": doc.model_dump(),
                        "parser_label": "local_pymupdf:floor",
                        "degraded": True,
                    }
                ),
            )
        except Exception as cache_err:
            logger.warning(f"Failed to cache floor parse result: {cache_err}")
        return ParseExecutionResult(
            structured_doc=doc,
            parser_label="local_pymupdf:floor",
            degraded=True,
            fallback_trail=fallback_trail,
            credits_charged=0,
            cache_hit=False,
        )

    def _build_chain(self, preferred: str, byok: bool) -> list[tuple[str, bool, bool]]:
        """Return (provider_name, is_paid, is_degraded) list.

        Owner-paid ``auto`` always tries Landing AI, then LlamaParse, then local.
        Visitor BYOK is bound to one named cloud parser so a LlamaParse key is
        never sent to Landing AI (and vice versa).
        """
        name = (preferred or "auto").strip().lower()

        if name in ("local_pymupdf", "local", "pymupdf"):
            return [("local_pymupdf", False, True)]

        if byok and name in ("landingai", "llamaparse"):
            return [
                (name, False, False),
                ("local_pymupdf", False, True),
            ]

        owner_paid = not byok
        if name == "llamaparse":
            return [
                ("llamaparse", owner_paid, False),
                ("landingai", owner_paid, False),
                ("local_pymupdf", False, True),
            ]

        # auto / landingai / default: Landing AI -> LlamaParse -> local PyMuPDF
        return [
            ("landingai", True if name == "auto" else owner_paid, False),
            ("llamaparse", True if name == "auto" else owner_paid, False),
            ("local_pymupdf", False, True),
        ]

    def _estimate_units(self, provider_name: str, info: dict[str, Any]) -> int:
        if provider_name == "landingai":
            return landing_units(info)
        if provider_name == "llamaparse":
            return llama_units(info)
        return 0

    def _build_buckets(
        self,
        provider_name: str,
        ctx: RequestContext,
        units: int,
        info: dict[str, Any],
    ) -> list[Bucket]:
        today = today_str()
        cycle = cycle_str()
        vid = visitor_bucket_id(ctx.session_id, ctx.client_ip)
        pages = info.get("pages", 1)

        if provider_name == "landingai":
            pool_key = landing_pool_key()
            return [
                Bucket(pool_key, units, usable_units("landing")),
                Bucket(f"day:landing:{today}", units, daily_cap_units("landing")),
                Bucket(f"u:{vid}:landing:{today}", units, VISITOR_ALLOWANCE["landing_units_day"]),
                Bucket(f"u:{vid}:pages:{today}", pages, VISITOR_ALLOWANCE["paid_pages_day"], adjustable=False),
            ]

        if provider_name == "llamaparse":
            pool_key = f"pool:llamaparse:{cycle}"
            return [
                Bucket(pool_key, units, usable_units("llamaparse")),
                Bucket(f"day:llamaparse:{today}", units, daily_cap_units("llamaparse")),
                Bucket(f"u:{vid}:llama:{today}", units, VISITOR_ALLOWANCE["llama_units_day"]),
                Bucket(f"u:{vid}:pages:{today}", pages, VISITOR_ALLOWANCE["paid_pages_day"], adjustable=False),
            ]

        return []

    def _resolve_key(self, provider_name: str, ctx: RequestContext) -> Secret | None:
        """Resolve API key: visitor BYOK secret takes precedence, else owner .env key."""
        if ctx.byok and ctx.parser_secret and ctx.parser_secret.reveal().strip():
            return ctx.parser_secret
        return owner_parser_key(provider_name, self.cfg)

    def _has_key_for_provider(self, provider_name: str, ctx: RequestContext) -> bool:
        """Check whether an active key exists for the given provider."""
        key = self._resolve_key(provider_name, ctx)
        return bool(key and key.reveal().strip())

    async def _call_provider(
        self,
        provider_name: str,
        pdf_path: Path,
        ctx: RequestContext,
        info: dict[str, Any],
    ) -> StructuredDoc:
        api_key = self._resolve_key(provider_name, ctx)
        if provider_name == "landingai":
            family, _tier = landing_route(info)
            doc = await self.landing_adapter.parse(
                pdf_path,
                api_key=api_key,
                model=LANDING_MODELS[family],
            )
            return doc
        if provider_name == "llamaparse":
            doc = await self.llama_adapter.parse(pdf_path, api_key=api_key)
            if doc.credits_units is None:
                doc.credits_units = llama_units(info)
            return doc
        return await self.local_adapter.parse(pdf_path)
