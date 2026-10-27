# Production Token & Credit Engineering Guide
**Stack:** Landing AI (default) → LlamaParse (fallback 1) → PyMuPDF (fallback 2, free)
**Mode:** Free-tier portfolio app with BYOK bypass
**Last verified:** 27 Oct 2026 (see §16 for what is verified vs. assumed)

---

## 0. TL;DR (the decisions this guide makes)

1. **Both free plans are small, finite pools.** Landing ≈ 1,000 credits, LlamaParse = 10,000 credits/month. Your architecture is a *pool-budgeting* problem, not just rate limiting.
2. **Never attach a payment method or Auto Recharge to these keys.** LlamaParse's Free plan has no pay-as-you-go and returns `402` when exhausted. Landing's Explore plan only spends credits you buy. Provider-side hard stops are your real safety net; your Redis ledger is the optimisation layer on top.
3. **Landing is your "premium showcase" lane, not your workhorse.** At ~1 credit/page it supports only a few dozen pages/day. **LlamaParse (≈3,300 pages/month at Cost-effective) is the workhorse. PyMuPDF is the infinite floor.**
4. **Route digital PDFs to Landing Verity (standard job)**, scanned PDFs to Landing Pro (standard job). This is ~3× cheaper per page than Pro and stretches the pool.
5. **Reserve → call → commit/release**, atomically, across visitor, daily, and pool buckets. Fail **closed** on paid providers if Redis is down.
6. **Cache by file hash.** Recruiters upload the same sample file. Repeats cost 0. Ship a pre-parsed sample.
7. **Always tell the user which parser produced the output** and flag degraded (PyMuPDF) results.

---

## 1. Two currencies, not one

| Currency | Billed by | Measured by |
|---|---|---|
| **Parser credits** | Landing AI, LlamaParse | Pages (+ output characters for Landing) |
| **LLM tokens** | Your chat / extraction model | Tokenizer estimate before, `usage` field after |

Tokenizer libraries are irrelevant for parsing. Parsers bill in pages and characters, so your estimator counts pages and characters. Tokens matter only once parsed markdown enters an LLM (§11).

---

## 2. Verified cost model

### 2.1 Landing AI (DPT-3 Parse)

Per page = **page rate + output-character rate**. Totals round **up** to the nearest 0.1 credit.

| Model / tier | Per page | Per 1,000 output chars |
|---|---|---|
| Pro, priority (sync or jobs) | 1.0 | 0.5 |
| Pro, **standard** (jobs only) | 0.5 | 0.25 |
| Verity, priority | 0.3 | 0.2 |
| Verity, **standard** (jobs only) | 0.15 | 0.1 |

- **Sync Parse always runs on priority (2× the cost).** Standard needs async Parse Jobs.
- **Verity** is a lower-latency *preview* model for digitally created text documents.
- Output characters = all Unicode code points in the returned `markdown`, including page-break and document-ID markers.
- **Credits are charged only on `200` and `206` responses.** Errors and timeouts (including `504`) are not billed. A `206` (some pages failed) *is* billed.
- The response tells you the truth: `metadata.billing.total_credits`, plus `page_count` and `output_markdown_chars`.
- **1 credit = US$0.01** (Landing's pricing explainer). So 1,000 free credits ≈ **$10 of value**.

### 2.2 LlamaParse (v2 tiers)

| Tier | Credits/page | Notes |
|---|---|---|
| Fast | 1 | Spatial text only, **no markdown** |
| Cost-effective | 3 | Markdown, AI-based. **Your fallback tier** |
| Agentic | 10 | |
| Agentic Plus | 45 | |

- Layout extraction: +3 credits/page.
- **$1.25 per 1,000 credits** on paid usage.
- Parsed files are cached **48 hours**; re-parsing the same file in that window is free.
- `target_pages` lets you parse only selected pages.

### 2.3 Worked example: one 3-page doc, ~2,000 output chars/page (6,000 total)

| Route | Credits | Landing $ at $0.01 |
|---|---|---|
| Landing Pro, priority (sync) | 3 + 3.0 = **6.0** | $0.06 |
| Landing Pro, standard (job) | 1.5 + 1.5 = **3.0** | $0.03 |
| Landing Verity, priority | 0.9 + 1.2 = **2.1** | $0.021 |
| Landing Verity, standard (job) | 0.45 + 0.6 = 1.05 → **1.1** | $0.011 |
| LlamaParse Cost-effective | **9** | $0.011 |

Per page at 2,000 chars/page: Pro priority 2.0, **Pro standard 1.0**, Verity priority 0.7, **Verity standard 0.35** credits.

---

## 3. Free-pool capacity planning (the core of this guide)

### 3.1 Pools

| Provider | Free pool | Resets? | Exhaustion behaviour |
|---|---|---|---|
| **LlamaParse Free** | **10,000 credits/month** | Yes, at next billing cycle | `402` "exceeded the maximum number of credits for your plan"; no pay-as-you-go on Free |
| **Landing AI** | **~1,000 credits** (as you stated) | **Unknown, treat as NON-renewing until your dashboard proves otherwise** | `402` "not enough credits" |

### 3.2 What the pools buy

| Provider / route | Credits per page | Pages from the whole pool | 3-page docs |
|---|---|---|---|
| Landing Pro priority (sync) | 2.0 | 500 | ~166 |
| Landing Pro standard | 1.0 | 1,000 | ~333 |
| Landing Verity standard | 0.35 | ~2,850 | ~950 |
| LlamaParse Cost-effective | 3 | 3,333 / month | ~1,111 / month |
| LlamaParse Agentic | 10 | 1,000 / month | ~333 / month |
| PyMuPDF | 0 | unlimited (CPU-bound) | unlimited |

(Based on 2,000 chars/page. Scanned pages assumed at 3,000 chars/page, so Pro standard is 1.25 credits/page.)

### 3.3 Budgeting rules

1. **Hold back a reserve.** Your own dev testing and playground use drain the *same* pool. Suggested: **15% reserve on Landing, 20% on LlamaParse.**
2. **Spread the burn.** Daily cap = usable ÷ 30. A pool that empties on day 3 gives day-4 recruiters the degraded path.

| | Pool | Reserve | Usable | Daily cap |
|---|---|---|---|---|
| Landing | 1,000 | 150 | 850 | **28 credits/day** (≈ 9 three-page Pro docs, or ≈ 25 Verity docs) |
| LlamaParse | 10,000 | 2,000 | 8,000 | **266 credits/day** (≈ 29 three-page docs) |

3. **If Landing's pool is one-time, also keep a lifetime cap** (the 850 usable) so it can't be drained past the reserve.
4. **Day buckets do not roll over.** Unused credits don't stack into tomorrow's allowance.
5. **Exhausted free plans are free to probe.** A `402` costs nothing, so a breaker that re-tries every 30 minutes is safe.

### 3.4 Visitor allowances (suggested starting point)

| Allowance (per visitor per day) | Value | Reason |
|---|---|---|
| Max pages per document | 3 | Bounds worst-case cost |
| Documents (uploads) | 5 | Includes cache hits; blocks abuse |
| Paid pages total | 10 | |
| **Premium (Landing) credits** | **6.0** | ≈ two 3-page Pro docs or five Verity docs |
| **LlamaParse credits** | **30** | ≈ ten pages |
| PyMuPDF | IP rate limit, e.g. 20 docs/hour | CPU protection |
| LLM tokens | 20,000 | §11 |

When a visitor's premium allowance is used up, the router skips Landing (reserve fails) and continues to LlamaParse, then PyMuPDF. Quality degrades gracefully with quota, never with surprise.

### 3.5 Capacity at these settings

| Lane | Global per day |
|---|---|
| Landing premium | ~9 (Pro std) to ~25 (Verity std) three-page docs |
| LlamaParse | ~29 three-page docs |
| PyMuPDF | Everyone else |
| Cached repeats and sample doc | Free |

For a portfolio this covers dozens of distinct recruiter uploads per day, and the lanes absorb each other's exhaustion.

---

## 4. Architecture

```
Upload
  │
  ▼
Gate 0 (free, local, PyMuPDF): size, page count ≤ 3, encrypted?, empty?, digital vs scanned
  │  reject early; cost 0
  ▼
BYOK key supplied? ──yes──► BYOK chain (THEIR keys only) ─► PyMuPDF
  │ no
  ▼
Dedup cache (sha256 + route) ──hit──► return, charge 0
  │ miss
  ▼
For each provider in [Landing, LlamaParse, PyMuPDF]:
    breaker open?            → skip
    reserve fails (any bucket: visitor / day / pool)?  → skip
    call (adapter handles backoff)
      ok        → commit actual, cache, return
      402       → release, trip quota breaker, next
      429/5xx   → release, count failure, next
      422/input → release, STOP (do not cascade)
  │
  ▼
Respond with markdown + provenance + remaining quota
```

---

## 5. Pre-flight estimation (free, local)

Run PyMuPDF on the upload before any paid call:

1. **Hard gates:** file size, page count (≤ 3 for free tier), encrypted, zero pages.
2. **Per page:** a text layer with more than ~100 characters = digital; otherwise scanned.
3. **Estimate output chars:** digital page ≈ extracted text length × **1.25** (markdown overhead; my assumption, so calibrate against real `output_markdown_chars`). Scanned page ≈ **3,000** chars.
4. **Worst-case reservation:** apply the §2 formulas to pages and estimated chars.
5. **Digital document** = at least 80% of pages digital.

---

## 6. Routing and model selection

| Document | Landing route | Why |
|---|---|---|
| Digital, text-heavy | **Verity, standard job** (pinned snapshot) | ~3× cheaper per page than Pro standard |
| Scanned / image-heavy | **Pro, standard job** | Verity targets digitally created documents |
| 1 page and instant feedback matters | Pro, priority (sync) | Pay 2× for latency only when tiny |
| BYOK | Their choice | Their money |

Notes:
- **Verity is a preview.** Put it behind a config flag so you can flip to Pro-only instantly. Test table quality on your own samples first.
- **Parse Jobs are async:** show a progress state, poll with backoff (or use webhooks).
- **LlamaParse fallback tier: Cost-effective.** Fast has no markdown, and PyMuPDF already covers the plain-text lane for free. Only offer Agentic on explicit user action.
- **PyMuPDF:**
  - No OCR by default. Scanned PDFs yield empty text; detect and return a clear message instead of an empty success.
  - AGPL-licensed (commercial licence available). Confirm that suits your project, or substitute pypdf/pdfplumber/pdfminer.six.

---

## 7. Fallback logic

### 7.1 Triggers

| Provider | Signal | Meaning | Action |
|---|---|---|---|
| Landing | **402** | Not enough credits | Trip quota breaker (30 min), next provider |
| Landing | **429** "temporarily exhausted" | Rate limit | Backoff 1-2 retries, then fall back for this request only |
| Landing | **429** "too large for tier" | Pages over per-request limit | Impossible if your page cap is below the limit; never retry |
| Landing | 502 / 503 | Transient infra (sync 502 not billed) | Backoff, then fall back; count toward failure breaker |
| Landing | 500 | All pages failed | Fall back |
| Landing | 504 | Sync timeout (475 s), not billed | Use jobs, or fall back |
| Landing | **206** | Some pages failed, **billed** | Accept; surface `failed_pages` |
| Landing | 401 | Bad/revoked key | Config error: alert, fall back |
| Landing | 422 | Bad input | **Don't cascade** |
| LlamaParse | **402** | Plan credits exhausted (no retry) | Trip quota breaker, next provider |
| LlamaParse | 429 | Rate limit; API sends **no `Retry-After`** | Exponential backoff with jitter |
| LlamaParse | 5xx | Transient | Retry, then fall back |
| LlamaParse | Job failures `PDF_IS_PROTECTED`, `PDF_IS_BROKEN`, `NO_DATA_FOUND_IN_FILE`, `TOO_MANY_PAGES` | Input problem | Don't cascade |
| LlamaParse | Job failure `TIMEOUT` | Slow | Fall back |

Branch on Landing's stable error `code` field, never on `message` text (the docs call wording variable).

### 7.2 Three layers of defence

1. **Ledger (proactive):** Redis counters decide *before* the call whether budget exists.
2. **Breaker (reactive):** a `402` or burst of 5xx flips a flag so you stop hammering a dead provider.
3. **Provider hard stops (final):** free plans cannot overspend. Keep it that way: **no card, no Auto Recharge** on these keys. Turn on provider usage alerts anyway.

### 7.3 Ledger drift

Your counters can disagree with the provider's real balance (playground testing, retries, 206s, rounding). The `402` breaker is the source of truth, and:
- Add an admin command to **re-sync a counter from the dashboard balance**.
- Alert if `actual_credits / estimated_credits` drifts outside, say, 0.7 to 1.1 over a day.

---

## 8. Reserve → commit → release

1. **Reserve** the worst case atomically across all buckets (visitor/day, visitor pages/day, provider/day, provider/pool).
2. **Call** the provider.
3. **Commit:** read actual (Landing: `metadata.billing.total_credits`; LlamaParse: pages × tier rate, reconciled against dashboard) and adjust each credit bucket by `actual − reserved`.
4. **Release** the whole reservation on any failure (failed calls aren't billed, so the counters must roll back).

Store Landing credits as **integer tenths** to avoid float drift. Fail **closed** (treat as budget-exhausted) if Redis errors.

---

## 9. LLM token engineering (downstream)

With parsed output of ~6,000 chars for 3 pages, the document is only ≈ 1,500 tokens (rule of thumb: chars ÷ 4). A 20,000-token daily visitor allowance therefore buys roughly 9 Q&A turns over one 3-page doc (about 1,500 doc + 200 question + 500 answer per turn).

1. **Clean markdown first:** strip page-break and doc-ID markers, collapse whitespace, remove base64 images.
2. **Cap input:** estimate tokens locally; truncate or chunk beyond your cap. If you use Anthropic, its token-counting endpoint gives exact counts.
3. **Always set `max_tokens`** on free-tier calls. Output is the pricier side.
4. **Charge actuals:** read `usage` (input + output) from the response and commit it to the visitor's token bucket.
5. **Model choice:** smallest, cheapest model you're happy with for the free tier (for Anthropic, Haiku: `claude-haiku-5-5`). BYOK: allowlist with the user's choice as default. Escalate only on explicit user action. Check current per-token prices yourself (not verified here).
6. **Prompt caching:** if users ask many questions about one document, cache the document block as a prefix.

---

## 10. BYOK rules

- A BYOK request **never falls back onto your keys.** Their chain: their Landing → their LlamaParse → PyMuPDF. Otherwise a quota error becomes a billing leak onto you.
- Pass keys per request; never log or store them; scrub headers/bodies from error logs.
- BYOK skips *your* credit quotas but still gets Gate 0 (size, pages, encrypted) and IP rate limits.

---

## 11. Visitor identity and abuse control

- Signed anonymous session cookie + hashed IP. Read the client IP from the proxy header set by *your* host (e.g. `x-forwarded-for`), and trust it only when the request came through that proxy.
- Shared NATs (offices, universities) share an IP: key quotas on the cookie primarily, IP secondarily.
- Optional bot gate (e.g. Cloudflare Turnstile) before the first paid call.
- Global **kill switch**: one Redis flag that forces PyMuPDF-only mode.

---

## 12. Reference implementation (Python / FastAPI + Redis)

Adapters call the official SDKs; the logic below is yours.

```python
# config.py
from dataclasses import dataclass
from math import ceil
from datetime import datetime, timezone

@dataclass(frozen=True)
class Rate:
    page: float
    per_1k: float

LANDING_RATES = {
    ("pro", "priority"):    Rate(1.0, 0.5),
    ("pro", "standard"):    Rate(0.5, 0.25),
    ("verity", "priority"): Rate(0.3, 0.2),
    ("verity", "standard"): Rate(0.15, 0.1),
}
LLAMA_CREDITS_PER_PAGE = {"fast": 1, "cost_effective": 3, "agentic": 10, "agentic_plus": 45}

# --- free pools (CONFIRM on your dashboards; see section 16) ---
POOLS = {
    "landing":    dict(total=1000,  reserve_pct=0.15, resets="never",   unit=10),  # tenths of a credit
    "llamaparse": dict(total=10000, reserve_pct=0.20, resets="monthly", unit=1),
}
def usable_units(p):  c = POOLS[p]; return int(c["total"] * (1 - c["reserve_pct"]) * c["unit"])
def daily_cap_units(p, days=30): return usable_units(p) // days

VISITOR = dict(
    max_pages_doc=3, docs_day=5, paid_pages_day=10,
    landing_units_day=60,      # 6.0 credits (tenths)
    llama_units_day=30,        # 30 credits
    llm_tokens_day=20_000,
)
SCANNED_CHARS_PER_PAGE = 3000
MD_OVERHEAD = 1.25             # calibrate vs metadata.output_markdown_chars

def today(): return datetime.now(timezone.utc).strftime("%Y-%m-%d")
def cycle(): return datetime.now(timezone.utc).strftime("%Y-%m")
def ceil_tenth(x): return ceil(x * 10 - 1e-9) / 10
```

```python
# estimator.py : free, local, runs before any paid call
import fitz  # PyMuPDF
from config import *

class InputRejected(Exception): ...

def analyse(pdf: bytes) -> dict:
    doc = fitz.open(stream=pdf, filetype="pdf")
    if doc.is_encrypted:                         raise InputRejected("encrypted_pdf")
    if doc.page_count == 0:                      raise InputRejected("empty_pdf")
    if doc.page_count > VISITOR["max_pages_doc"]: raise InputRejected("too_many_pages")
    chars, digital = 0, 0
    for page in doc:
        n = len(page.get_text().strip())
        if n > 100: digital += 1; chars += int(n * MD_OVERHEAD)
        else:       chars += SCANNED_CHARS_PER_PAGE
    return dict(pages=doc.page_count, est_chars=chars,
                digital=digital / doc.page_count >= 0.8)

def landing_route(info):                         # (model, tier)
    return ("verity", "standard") if info["digital"] else ("pro", "standard")

def landing_units(info):                         # integer tenths of a credit
    m, t = landing_route(info); r = LANDING_RATES[(m, t)]
    return int(ceil_tenth(info["pages"] * r.page + info["est_chars"] / 1000 * r.per_1k) * 10)

def llama_units(info, tier="cost_effective"):
    return info["pages"] * LLAMA_CREDITS_PER_PAGE[tier]
```

```python
# ledger.py : atomic multi-bucket reserve (per-bucket amount and limit)
from dataclasses import dataclass

RESERVE_LUA = """
local ttl = tonumber(ARGV[1])
for i = 1, #KEYS do
  local cur = tonumber(redis.call('GET', KEYS[i]) or '0')
  if cur + tonumber(ARGV[2*i]) > tonumber(ARGV[2*i+1]) then return i end
end
for i = 1, #KEYS do
  local n = redis.call('INCRBY', KEYS[i], ARGV[2*i])
  if n == tonumber(ARGV[2*i]) then redis.call('EXPIRE', KEYS[i], ttl) end
end
return 0
"""

@dataclass
class Bucket:
    key: str
    amount: int
    limit: int
    adjustable: bool = True      # False for page counters

class Ledger:
    def __init__(self, redis): self.r = redis

    async def reserve(self, buckets: list[Bucket], ttl=3_000_000) -> tuple[bool, str | None]:
        try:
            args = [ttl]
            for b in buckets: args += [b.amount, b.limit]
            res = await self.r.eval(RESERVE_LUA, len(buckets), *[b.key for b in buckets], *args)
            return (res == 0, None if res == 0 else buckets[res - 1].key)
        except Exception:
            return (False, "redis_down")          # fail CLOSED on paid providers

    async def commit(self, buckets, actual_units: int):
        for b in buckets:
            if b.adjustable: await self.r.incrby(b.key, actual_units - b.amount)

    async def release(self, buckets):
        for b in buckets: await self.r.incrby(b.key, -b.amount)
```

```python
# breaker.py
class Breaker:
    def __init__(self, redis): self.r = redis

    async def is_open(self, provider):
        try:    return bool(await self.r.exists(f"cb:{provider}"))
        except: return True                       # unknown => treat as open

    async def trip_quota(self, provider, ttl=1800):   # 402s are free to re-probe
        await self.r.set(f"cb:{provider}", "quota", ex=ttl)

    async def record_failure(self, provider, threshold=5, window=60, open_for=60):
        n = await self.r.incr(f"cbf:{provider}")
        if n == 1: await self.r.expire(f"cbf:{provider}", window)
        if n >= threshold: await self.r.set(f"cb:{provider}", "errors", ex=open_for)
```

```python
# providers.py : buckets per provider (adapters only wrap SDK calls + error mapping)
from config import *
from ledger import Bucket

class QuotaExhausted(Exception): ...     # 402 from either provider
class Transient(Exception): ...          # 5xx / timeouts / 429 after retries

class Landing:
    name, paid, degraded = "landing", True, False
    def estimate(self, info): return landing_units(info)
    def buckets(self, ctx, units, info):
        pool = "pool:landing:lifetime" if POOLS["landing"]["resets"] == "never" else f"pool:landing:{cycle()}"
        return [
            Bucket(pool,                         units, usable_units("landing")),
            Bucket(f"day:landing:{today()}",     units, daily_cap_units("landing")),
            Bucket(f"u:{ctx.vid}:landing:{today()}", units, VISITOR["landing_units_day"]),
            Bucket(f"u:{ctx.vid}:pages:{today()}", info["pages"], VISITOR["paid_pages_day"], adjustable=False),
        ]
    # async parse(pdf, info): submit Parse Job (standard tier, pinned model), poll,
    # map 402->QuotaExhausted, 422->InputRejected, 429/5xx/timeout->Transient,
    # return markdown + units=round(metadata.billing.total_credits*10)

class LlamaParse:
    name, paid, degraded = "llamaparse", True, False
    def estimate(self, info): return llama_units(info)
    def buckets(self, ctx, units, info):
        return [
            Bucket(f"pool:llamaparse:{cycle()}",  units, usable_units("llamaparse")),
            Bucket(f"day:llamaparse:{today()}",   units, daily_cap_units("llamaparse")),
            Bucket(f"u:{ctx.vid}:llama:{today()}", units, VISITOR["llama_units_day"]),
            Bucket(f"u:{ctx.vid}:pages:{today()}", info["pages"], VISITOR["paid_pages_day"], adjustable=False),
        ]
    # async parse(): Cost-effective tier; 402->QuotaExhausted; 429 exponential backoff + jitter;
    # units = pages * 3 (reconcile against dashboard)

class PyMuPDFLocal:
    name, paid, degraded = "pymupdf", False, True
    # estimate -> 0; buckets -> []; parse(): pymupdf4llm / get_text; detect scanned => clear error text
```

```python
# router.py
class AllProvidersFailed(Exception): ...

async def parse_with_fallback(pdf, info, ctx, chain, ledger, breaker, cache):
    key = f"parse:{ctx.sha}:{info['digital']}"
    if hit := await cache.get(key):
        return {**hit, "credits_charged": 0, "cache": True}

    trail = []
    for p in chain:                               # [Landing(), LlamaParse(), PyMuPDFLocal()]
        if p.paid and await breaker.is_open(p.name):
            trail.append((p.name, "breaker_open")); continue

        buckets, units = [], 0
        if p.paid and not ctx.byok:
            units = p.estimate(info)
            buckets = p.buckets(ctx, units, info)
            ok, failed_key = await ledger.reserve(buckets)
            if not ok:
                trail.append((p.name, f"budget:{failed_key}")); continue
        try:
            res = await p.parse(pdf, info, ctx)   # adapter does backoff for 429/5xx
        except InputRejected:
            await ledger.release(buckets); raise  # user's file is the problem: stop
        except QuotaExhausted:
            await ledger.release(buckets)
            await breaker.trip_quota(p.name)
            trail.append((p.name, "quota_exhausted")); continue
        except Transient:
            await ledger.release(buckets)
            await breaker.record_failure(p.name)
            trail.append((p.name, "transient")); continue

        if buckets: await ledger.commit(buckets, res.units)    # actual vs reserved
        out = dict(markdown=res.markdown, parser=res.label, degraded=p.degraded,
                   trail=trail, failed_pages=res.failed_pages, credits_units=res.units)
        await cache.set(key, out, ex=86_400)
        return out
    raise AllProvidersFailed(trail)
```

---

## 13. Response contract and UX

```json
{
  "markdown": "...",
  "meta": {
    "parser": "landing:dpt-3-verity:standard",
    "degraded": false,
    "fallback_trail": [["landing", "quota_exhausted"], ["llamaparse", "ok"]],
    "credits_charged": 9,
    "cache": false,
    "failed_pages": []
  },
  "quota": {
    "premium_credits_left_today": 4.9,
    "paid_pages_left_today": 7,
    "tokens_left_today": 14500
  }
}
```

- When `degraded` is true, show: *"Basic text extraction: tables and scanned pages may be missing."* Never present PyMuPDF output as premium parsing.
- Ship a **pre-parsed sample PDF** (zero credits). Recruiters click it first.
- Quota gauge: "Premium parses left today: 1 · Standard: 7 pages."
- When all free lanes are used, offer the BYOK toggle.

---

## 14. Observability

One structured log line per request: provider, model, tier, pages, estimated vs actual units, latency, fallback trail, cache hit, visitor id (hashed). Alerts at 50/80/100% of each daily and pool budget. Weekly review of estimate-vs-actual drift to tune `MD_OVERHEAD`.

---

## 15. Pre-launch test checklist

1. Mock provider returning `402`, `429`, `502`, `504`, `206`: assert the chain behaves per §7.1.
2. 50 parallel requests against a nearly-full bucket: reserve never oversells.
3. Redis down: paid providers disabled, PyMuPDF still serves (fail closed).
4. Scanned PDF on the PyMuPDF path returns the explicit "scanned not supported" message.
5. Duplicate upload hits the cache, charges 0.
6. BYOK key with exhausted quota never touches your keys.
7. Visitor exhausts premium allowance: next upload lands on LlamaParse, then PyMuPDF.
8. Force `402` from Landing: breaker opens, re-probes after TTL, recovers.
9. Pool counters re-synced from dashboard via admin command.
10. Verity vs Pro on your 5 real sample documents: compare tables before making Verity default.

---

## 16. Verification status (be honest about what's checked)

| Item | Status |
|---|---|
| Landing per-page and per-char rates, tiers, rounding, billing-on-200/206-only | **Verified** from Landing credit-consumption and parse-troubleshoot docs |
| Landing 1 credit = US$0.01 | **Verified** (Landing pricing explainer) |
| Landing error semantics: 402 insufficient credits, 429 two cases, 206 billed | **Verified** |
| LlamaParse tier credits, $1.25/1,000, 48 h cache | **Verified** from LlamaParse pricing |
| LlamaParse Free = 10,000 credits/month, `402` at exhaustion, no pay-as-you-go on Free | **Verified** from LlamaParse billing docs and pricing pages |
| LlamaParse 429 has no `Retry-After` | **Verified** from error reference |
| **Landing free pool = 1,000 credits** | **User-stated. Not confirmed for ADE.** Landing's ADE docs say new accounts start on the Explore plan with "free credits" without giving a number in what I could read. The "1,000 credits/month" figure I found belongs to LandingLens, a different product, and a third-party listing describes ADE as free-trial rather than a permanent free plan. **Check va.landing.ai/plan and whether credits renew**; flip `resets` in `POOLS` accordingly |
| Landing per-request page limits and rate limits | **Not checked.** See Landing's Rate Limits page; confirm your 3-page cap is well under them |
| Verity table quality | **Not tested** |
| LlamaParse parse result exposes actual billed credits | **Not confirmed** for Parse (Extract exposes `num_pages_billed`); compute pages × rate and reconcile |
| Per-token pricing of your LLM | **Not checked** |
| `MD_OVERHEAD = 1.25` | **My assumption.** Calibrate |

---

*Next steps: confirm the Landing pool and whether it resets, set the `POOLS` config, build the three adapters, run the §15 checklist.*
