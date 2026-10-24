# Architecture Decisions Log (ADR)

## Decision 1: Access Tiers and Financial Isolation
- **Tier A (Demo):** Free, immediate access with zero keys. Runs against a pre-indexed `scope = "demo"` corpus. Paid by the owner key (tight daily & per-session caps).
- **Tier B (Upload):** Visitor uploads a PDF. Parsing is handled either via a free local parser (PyMuPDF) or visitor-supplied parser key (BYOK: LlamaParse, Landing AI, Unstructured). Embeddings and reranking use the owner's Cohere key within caps.
- **Tier C (Full BYOK):** Visitor brings their own LLM API key in addition to Tier B. Generation costs the owner $0. Higher query caps.

## Decision 2: BYOK Scope Bound to Exactly Two Services
- BYOK is strictly limited to:
  1. PDF Parser (job-scoped, memory only)
  2. Answer LLM (request-scoped, header only)
- Vector DB (Qdrant) and Embeddings/Reranking (Cohere) are hosted/managed on the owner's infrastructure with hard caps.
- **Consequence:** Eliminates SSRF vectors (no user-supplied endpoints), avoids embedding dimension mismatch, enables deterministic TTL cleanup.

## Decision 3: Single Provider for Embeddings & Reranking
- **Provider:** Cohere (pinned embedding model e.g. `embed-english-v3.0` / `rerank-v3.5`).
- Single owner key with hard provider-side budgets set before launch.
- If `embedding_version` changes, demo corpus is re-indexed and visitor sessions expire.

## Decision 4: Egress Allowlist vs SSRF Guard
- All outbound requests to AI providers pass through an egress allowlist:
  - `api.cohere.com`
  - `api.cloud.llamaindex.ai`
  - `api.landing.ai`
  - `api.unstructured.io`
  - `api.groq.com`
  - `api.openai.com`
  - `api.anthropic.com`
- Direct IP addresses, private subnets (RFC 1918), loopback, link-local metadata (`169.254.169.254`), and arbitrary domains are blocked at the transport layer.

## Decision 5: Ephemeral Key Lifecycle & Zero Persistence
- Visitor keys are wrapped in a `Secret` type (`str`/`repr`/JSON serialize to `"***"`).
- Visitor keys are never written to disk, SQLite/Postgres, Redis, logs, error traces, or cache keys.
- Parser keys exist only in memory during job execution and are destroyed in a `finally` block.
- LLM keys exist only within request-scoped contextvars and are garbage-collected upon response completion.
- Logging middleware and exception handlers redact all credentials.

## Decision 6: Error Taxonomy & Fail-Fast Policy
- Visitor key errors (invalid key, quota exceeded) fail fast with clear UI messages and are **never retried**.
- Owner key rate limits use bounded exponential backoff with a circuit breaker.

## Decision 7: Owner Spend Caps & Financial Thresholds
Owner financial limits are configured in `.env` and enforced across sessions and daily operations:
- **Per-Session Limits:**
  - Maximum Chunks Embedded: 1,500 chunks
  - Maximum Rerank Calls: 30 calls
  - Maximum Questions (Owner Default LLM): 15 questions
  - Maximum Questions (Visitor BYOK LLM): 100 questions
  - Maximum Documents per Session: 3 documents
  - Maximum Total Pages per Session: 30 pages
  - Session TTL: 2 hours (hard deletion of vectors, SQL rows, and cached parsed files)
- **Daily Global Limits (Owner Kill Switch Protection):**
  - Maximum Chunks Embedded: 25,000 chunks/day
  - Maximum Rerank Calls: 500 calls/day
  - Maximum Owner LLM Tokens: 500,000 tokens/day
  - Maximum Jobs: 100 jobs/day

## Decision 8: Quality Gate Calibrated Thresholds
Parsed documents undergo local quality evaluation before chunking and embedding:
- **Text Coverage Ratio:** Minimum 0.65, Maximum 2.5 compared to PyMuPDF plain-text extraction. Outside this range flags incomplete parsing or duplication.
- **Heading Sanity:** Documents with >= 4 pages and 0 headings, or documents with > 3 erratic level jumps (e.g., H1 -> H5) trigger quality warnings.
- **Empty Pages:** If > 30% of pages yield no extracted blocks, a warning is raised.
- **Garbled Text Density:** If > 3% of characters are replacement characters (`\ufffd`) or unprintable private-use unicode, a warning is raised.
- **Non-blocking Behavior:** Warnings notify the visitor and suggest trying an alternative parser (or local parser fallback), but do not discard the parse.
