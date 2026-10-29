"""Single source of truth for parser credits, LLM tokens, and visitor allowances.

Every cap in OwnerConfig, the ledger, Gate 0, and token-engineering-guide.md
must read from this module. Do not duplicate these numbers elsewhere.

Landing pool size is user-stated and unconfirmed for ADE/DPT-3. Until the
dashboard proves a monthly reset, treat it as a one-shot lifetime pool.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil


@dataclass(frozen=True)
class Rate:
    """Per-page and per-1k-output-character credit rate."""

    page: float
    per_1k: float


# Landing AI DPT-3 Parse rates. Per page = page rate + output-character rate.
LANDING_RATES: dict[tuple[str, str], Rate] = {
    ("pro", "priority"): Rate(1.0, 0.5),
    ("pro", "standard"): Rate(0.5, 0.25),
    ("verity", "priority"): Rate(0.3, 0.2),
    ("verity", "standard"): Rate(0.15, 0.1),
}

LANDING_MODELS: dict[str, str] = {
    "verity": "dpt-3-verity-latest",
    "pro": "dpt-3-pro-latest",
}

LANDING_SERVICE_TIER = "standard"
LANDING_JOBS_HOST = "https://api.ade.landing.ai"
LANDING_JOBS_CREATE_URL = f"{LANDING_JOBS_HOST}/v2/parse/jobs"
LANDING_JOBS_GET_URL = f"{LANDING_JOBS_HOST}/v2/parse/jobs"

# LlamaParse credits per page
LLAMA_CREDITS_PER_PAGE: dict[str, int] = {
    "fast": 1,
    "cost_effective": 3,
    "agentic": 10,
    "agentic_plus": 45,
}

# Free pool capacities and safety reserves.
# Landing total=1000 is unconfirmed; pool_confirmed=False forces one-shot budgeting.
POOLS: dict[str, dict[str, int | float | str | bool]] = {
    "landing": {
        "total": 1000,
        "reserve_pct": 0.15,
        "resets": "never",
        "pool_confirmed": False,
        "unit": 10,  # integer tenths of a credit
    },
    "llamaparse": {
        "total": 10000,
        "reserve_pct": 0.20,
        "resets": "monthly",
        "pool_confirmed": True,
        "unit": 1,
    },
}

# Per-visitor and per-session allowances (the only copy of these numbers).
VISITOR_ALLOWANCE = {
    "max_pages_doc": 30,
    "docs_day": 10,
    "session_max_documents": 3,
    "session_max_total_pages": 30,
    "session_max_chunks_embedded": 1500,
    "session_max_rerank_calls": 30,
    "session_max_questions_owner_llm": 15,
    "session_max_questions_own_llm": 100,
    "paid_pages_day": 15,
    "landing_units_day": 60,  # 6.0 credits in tenths
    "llama_units_day": 30,  # 30 credits
    "llm_tokens_day": 50_000,
}

# Owner-global daily caps (spread across all visitors).
DAILY_GLOBAL = {
    "max_chunks_embedded": 25_000,
    "max_rerank_calls": 500,
    "max_owner_llm_tokens": 500_000,
    "max_jobs": 100,
}

SCANNED_CHARS_PER_PAGE = 3000
MD_OVERHEAD = 1.25
PARSE_CACHE_TTL_SECONDS = 7 * 24 * 3600
GLOBAL_PARSE_CACHE_PARSER = "any"
GLOBAL_PARSE_CACHE_VERSION = "v1"


def usable_units(provider: str) -> int:
    """Compute total usable units for a pool after deducting safety reserve."""
    cfg = POOLS[provider]
    return int(cfg["total"] * (1 - float(cfg["reserve_pct"])) * int(cfg["unit"]))


def daily_cap_units(provider: str, days: int = 30) -> int:
    """Compute maximum usable units per day to spread pool over billing cycle."""
    return usable_units(provider) // days


def today_str() -> str:
    """UTC date string YYYY-MM-DD."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def cycle_str() -> str:
    """UTC billing cycle string YYYY-MM."""
    return datetime.now(UTC).strftime("%Y-%m")


def ceil_tenth(val: float) -> float:
    """Round up to the nearest tenth of a credit (Landing AI billing rule)."""
    return ceil(val * 10 - 1e-9) / 10


def landing_credits_to_units(total_credits: float) -> int:
    """Convert Landing billed credits into integer tenths stored by the ledger."""
    return int(round(ceil_tenth(float(total_credits)) * 10))


def visitor_bucket_id(session_id: str, client_ip: str) -> str:
    """Stable-enough visitor id for daily credit/token buckets."""
    return hashlib.md5(f"{session_id}:{client_ip}".encode()).hexdigest()[:12]


def landing_pool_key() -> str:
    """Lifetime key until the Landing pool is confirmed to reset."""
    resets = str(POOLS["landing"].get("resets") or "never")
    if resets == "never" or not POOLS["landing"].get("pool_confirmed"):
        return "pool:landing:lifetime"
    if resets == "monthly":
        return f"pool:landing:{cycle_str()}"
    return f"pool:landing:{today_str()}"
