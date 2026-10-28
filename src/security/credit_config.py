"""Credit and Token Engineering configuration.

Adheres strictly to token-engineering-guide.md:
- Parser rates for Landing AI (DPT-3 Pro & Verity) and LlamaParse (Fast, Cost-effective, Agentic)
- Free pool capacities, reserves, and daily budget spread
- Per-visitor allowances
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil


@dataclass(frozen=True)
class Rate:
    """Per-page and per-1k-output-character credit rate."""

    page: float
    per_1k: float


# Landing AI DPT-3 Parse Rates
# Per page = page rate + output-character rate (1,000 characters)
LANDING_RATES: dict[tuple[str, str], Rate] = {
    ("pro", "priority"): Rate(1.0, 0.5),
    ("pro", "standard"): Rate(0.5, 0.25),
    ("verity", "priority"): Rate(0.3, 0.2),
    ("verity", "standard"): Rate(0.15, 0.1),
}

# LlamaParse Credits Per Page
LLAMA_CREDITS_PER_PAGE: dict[str, int] = {
    "fast": 1,
    "cost_effective": 3,
    "agentic": 10,
    "agentic_plus": 45,
}

# Free Pool Capacities & Safety Reserves
# Landing: ~1,000 credits lifetime / non-renewing pool (15% reserve)
# LlamaParse: 10,000 credits/month (20% reserve)
POOLS: dict[str, dict[str, int | float | str]] = {
    "landing": {
        "total": 1000,
        "reserve_pct": 0.15,
        "resets": "never",
        "unit": 10,  # Stored in integer tenths of a credit to eliminate float drift
    },
    "llamaparse": {
        "total": 10000,
        "reserve_pct": 0.20,
        "resets": "monthly",
        "unit": 1,
    },
}

# Per-Visitor Daily Allowances
VISITOR_ALLOWANCE = {
    "max_pages_doc": 30,  # Supports up to 30 pages per doc
    "docs_day": 10,
    "paid_pages_day": 15,
    "landing_units_day": 60,  # 6.0 credits (in tenths)
    "llama_units_day": 30,  # 30 credits
    "llm_tokens_day": 50_000,
}

SCANNED_CHARS_PER_PAGE = 3000
MD_OVERHEAD = 1.25


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
