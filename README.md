# Provenance RAG

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0+-green.svg)](https://fastapi.tiangolo.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-2.9.0+-blue.svg)](https://docs.pydantic.dev/)
[![Pytest](https://img.shields.io/badge/pytest-175%20passed-brightgreen.svg)](https://docs.pytest.org/)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

> A production-grade, financially isolated Retrieval-Augmented Generation (RAG) framework designed to eliminate wallet drain, protect visitor API keys, prevent SSRF attacks, and guarantee document parsing quality before embedding.

---

## 📖 Table of Contents
1. [The Problem This Project Solves](#-the-problem-this-project-solves)
2. [The 3-Tier Access System](#-the-3-tier-access-system)
3. [End-to-End Visual Architecture](#-end-to-end-visual-architecture)
4. [🏛️ Phase 0: Foundation, Architecture Decisions & Workspace Setup](#️-phase-0-foundation-architecture-decisions--workspace-setup)
5. [🛡️ Phase 1: Key Safety, Credential Isolation & Egress Firewall](#️-phase-1-key-safety-credential-isolation--egress-firewall)
6. [📑 Phase 2: Parser Layer, Universal Normalization & Quality Gate](#-phase-2-parser-layer-universal-normalization--quality-gate)
7. [🧩 Phase 3: Hybrid Chunker, Heading Fusion, Dual Embeddings & Qdrant Storage](#-phase-3-hybrid-chunker-heading-fusion-dual-embeddings--qdrant-storage)
8. [🎯 Phase 4: Hybrid Retrieval, Cohere Rerank, Generation & Interactive CLI](#-phase-4-hybrid-retrieval-cohere-rerank-generation--interactive-cli)
9. [🌐 Phase 5: REST API, Sessions, Demo Mode & Owner Cost Controls](#-phase-5-rest-api-sessions-demo-mode--owner-cost-controls)
10. [📤 Phase 6: Upload Flow, Asynchronous Jobs & Data Lifecycle](#-phase-6-upload-flow-asynchronous-jobs--data-lifecycle)
11. [📊 Phase 7: Evaluation, Tuning & Privacy-Safe Tracing](#-phase-7-evaluation-tuning--privacy-safe-tracing)
12. [🔍 Real-World Walkthrough: Trace of an Uploaded Document](#-real-world-walkthrough-trace-of-an-uploaded-document)
13. [🗺️ Codebase Directory Map (Organized by Phase)](#️-codebase-directory-map-organized-by-phase)
14. [🚀 How to Run and Verify](#-how-to-run-and-verify)
15. [📈 Master Roadmap & Phase-by-Phase Progress](#-master-roadmap--phase-by-phase-progress)

---

## 💡 The Problem This Project Solves

Most open-source RAG projects fail in one of three ways when deployed publicly:

1. **The "Wallet Drain" Disaster:** If you host a live demo that uses your own OpenAI or Claude keys, a single user or bot can loop questions and drain your credit card overnight.
2. **The "Clunky Setup" Problem:** If you force visitors to enter 5 different API keys (parser, embedder, vector DB, reranker, LLM) just to test the app, 99% of people will leave.
3. **The "Garbage In, Garbage Out" Trap:** PDFs are messy. Multi-column layouts, tables, repeated headers (`"Page 1 of 50"`), and OCR glitches silently corrupt vector search.

**Provenance RAG solves all three:**
* **Hybrid Access:** Visitors can test the system immediately with **zero keys** (Tier A), upload documents with a **free local parser** (Tier B), or bring their **own LLM key** for unlimited turns (Tier C).
* **Hard Cost Boundaries:** Embeddings and reranking are strictly capped on a single owner key (**Cohere**). Parsing and heavy generation are offloaded or run locally for free.
* **Leak-Proof Security:** Visitor keys are kept in memory only, shielded behind an egress firewall, and automatically shredded after use.
* **Automated Quality Inspector:** A pre-embedding Quality Gate catches dropped text or broken tables before anything touches the vector database.

---

## 👥 The 3-Tier Access System

| Tier | Name | What the Visitor Supplies | What the Visitor Can Do | Who Pays for What? |
|---|---|---|---|---|
| **Tier A** | **Instant Demo** | **Nothing** (zero keys required) | Ask questions over a pre-indexed demo corpus (`scope = "demo"`) | **Owner pays** for Cohere embedding, reranking, and default LLM answers (tight per-session & per-IP caps). |
| **Tier B** | **Document Upload** | A PDF + Free Local Parser **or** Visitor's Parser Key | Upload any PDF, parse it, index it into a private session, and chat | **Visitor pays** for parsing (or uses the free local parser for $0). **Owner pays** for embedding & rerank within caps. |
| **Tier C** | **Full BYOK** | PDF + Parser Key + **Own LLM Key** | Same as Tier B, but answers are generated using the visitor's own LLM key (Groq, OpenAI, Anthropic) | **Visitor pays** for parsing and text generation. **Owner pays** only for embedding & reranking within caps. |

---

## 🏗️ End-to-End Visual Architecture

```
                                  [ VISITOR ]
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
   [ INGESTION PIPELINE ]                                 [ CHAT PIPELINE ]
1. Upload PDF (Check magic bytes)                     1. User Query (Derive session scope)
2. Fast Page Count (PyMuPDF in 5ms, $0)               2. Rate Limits & Spend Caps Check
3. Pick Parser (Local / LlamaParse / Landing AI)      3. Query Rewrite (if follow-up)
4. Parse Document into Blocks                         4. Cohere Embed (Query vector)
5. Clean Text & Strip Running Headers                 5. Hybrid Search (Dense + Sparse in Qdrant)
6. Quality Gate Audit (Coverage & Headings)           6. Cohere Rerank (Top 5 candidates)
7. Hybrid Chunker (Parent-Child + Fusion)             7. Not-Found Gate (Score < threshold? Exit!)
8. Cohere Embed (Owner key) -> Qdrant Store           8. Context Expansion (Parent text retrieval)
9. Parser Key Shredded from RAM                       9. LLM Generation (Owner default or Visitor key)
                                                      10. Citation Check & Streaming Output
```

---

## 🏛️ Phase 0: Foundation, Architecture Decisions & Workspace Setup

> **Phase 0 Goal:** Establish the repository structure, toolchains, git hygiene, budget controls, and interface contracts before writing any pipeline code.

### 1. Architecture Decision Records (`docs/DECISIONS.md`)
We locked the foundational decisions upfront:
* **BYOK Scope Bound to Exactly 2 Services:** The visitor can only supply credentials for (1) PDF Parser and (2) Answer LLM. All vector embeddings (Cohere Embed), reranking (Cohere Rerank), and vector storage (Qdrant) remain on owner-managed infrastructure.
* **SSRF Elimination by Design:** Because visitors cannot provide arbitrary vector database URLs or custom webhook hosts, the system has zero SSRF surface area.
* **Pinned Embedding Model:** Cohere's `embed-english-v3.0` is pinned via `EMBEDDING_VERSION = "emb-v1"`. If changed, the demo corpus is re-indexed and visitor sessions expire.

### 2. Owner Spend Controls & Caps (`.env.example` & `src/security/config.py`)
To prevent cloud provider bills from exploding, the owner configuration enforces hard mathematical limits:
* **Per-Session Caps:** Max 1,500 embedded chunks, 30 rerank calls, 15 owner-funded LLM questions, 100 BYOK questions, 3 documents, 30 total pages.
* **Daily Global Caps:** Max 25,000 chunks embedded, 500 rerank calls, 500,000 owner LLM tokens, 100 ingestion jobs.
* **Emergency Kill Switches:** Config flags (`KILL_SWITCH_ACTIVE`, `KILL_SWITCH_DISABLE_UPLOADS`, `KILL_SWITCH_DISABLE_OWNER_LLM`) that instantly shut off paid services without redeploying code.

### 3. Core Decoupled Contracts (`src/interfaces.py`)
Defines standard abstract base classes (`IParser`, `IChunker`, `IEmbedder`, `IReranker`, `ILLM`). Downstream business logic relies exclusively on these contracts rather than concrete vendor SDKs.

---

## 🛡️ Phase 1: Key Safety, Credential Isolation & Egress Firewall

> **Phase 1 Goal:** Construct an ironclad security moat that handles untrusted visitor API keys in RAM only, prevents key leaks in logs and stack traces, and enforces an outbound network firewall.

```
[ Visitor API Key ]
        │
        ▼
┌─────────────────────────┐
│ 1. Secret Invisibility  │  str(key) -> "***"
└───────────┬─────────────┘  JSON dump -> "***"
            │
            ▼
┌─────────────────────────┐
│ 2. Redaction Filter     │  Logs & exceptions scrubbed for:
└───────────┬─────────────┘  "Bearer ...", "sk-...", "llx-...", "co-..."
            │
            ▼
┌─────────────────────────┐
│ 3. Egress Allowlist     │  Blocks outbound traffic to anything
└───────────┬─────────────┘  except: api.cohere.com, api.landing.ai, etc.
            │
            ▼
┌─────────────────────────┐
│ 4. Memory Shredder      │  LLM keys: bound to request contextvars.
└─────────────────────────┘  Parser keys: destroyed in job finally block.
```

### 1. The Invisibility Cloak (`src/security/secret.py`)
* **What it does:** Wraps sensitive strings in a `Secret` class.
* **Why it matters:** If an engineer accidentally writes `logger.info(f"Connecting with {key}")`, a plain string leaks to disk. With `Secret`:
  ```python
  key = Secret("sk-live-secret-key-12345")
  print(key)  # Prints: ***
  print(repr(key))  # Prints: Secret('***')
  dict_payload = {"key": key}
  json.dumps(...)  # Serializes as: {"key": "***"}
  ```
  The raw value can only be retrieved by explicitly invoking `key.reveal()`, which is called solely when constructing the final HTTP request to the authorized provider.

### 2. Defense-in-Depth Redaction Engine (`src/security/redaction.py`)
* **What it does:** Scans text, dictionaries, and Python logging records using regular expressions.
* **Why it matters:** Even if an unhandled library exception or stack trace contains a raw credential, the filter scrubs it before it reaches console or log files:
  * `sk-[a-zA-Z0-9_\-]{16,}` $\to$ `[REDACTED_OPENAI_KEY]`
  * `co-[a-zA-Z0-9_\-]{16,}` $\to$ `[REDACTED_COHERE_KEY]`
  * `llx-[a-zA-Z0-9_\-]{16,}` $\to$ `[REDACTED_LLAMAPARSE_KEY]`
  * `gsk_[a-zA-Z0-9_\-]{16,}` $\to$ `[REDACTED_GROQ_KEY]`
  * `anthropic-[a-zA-Z0-9_\-]{16,}` $\to$ `[REDACTED_ANTHROPIC_KEY]`
  * `Authorization: Bearer <token>` $\to$ `Authorization: Bearer [REDACTED]`

### 3. Outbound Egress Firewall (`src/security/egress.py`)
* **What it does:** Enforces a strict domain allowlist on all outbound HTTP calls.
* **The Threat:** Attackers often try **SSRF (Server-Side Request Forgery)** by tricking a server into fetching `http://169.254.169.254/latest/meta-data/` to steal AWS/cloud credentials, or targeting `http://localhost:8000` to manipulate internal APIs.
* **How We Block It:** Our custom `SecureHttpClient` validates the target URL *before* opening a network socket:
  * **Allowed:** `api.cohere.com`, `api.cohere.ai`, `api.cloud.llamaindex.ai`, `api.landing.ai`, `api.va.landing.ai`, `api.unstructured.io`, `api.groq.com`, `api.openai.com`, `api.anthropic.com`.
  * **Blocked:** All direct IP addresses (RFC 1918 private subnets, loopback `127.0.0.1`, cloud metadata `169.254.169.254`), non-HTTPS schemes, and arbitrary domains. Attempted violations raise `EgressBlockedError` instantly.

### 4. Memory-Only Shredder (`src/security/context.py`)
* **What it does:** Dictates the lifespan of visitor credentials in RAM.
* **Visitor LLM Keys:** Bound to Python `contextvars` for the active HTTP request. When the chat stream finishes, the context variable is reset. The key vaporizes.
* **Visitor Parser Keys:** Passed to `EphemeralJobContext` in memory during background parsing. As soon as the document is parsed into blocks, the `finally` block executes:
  ```python
  with EphemeralJobContext(parser_name="llamaparse", parser_key=key) as job:
      # Parse document...
  # Key is now None in memory; accessing it raises RuntimeError!
  ```
  Keys are **never** written to SQLite, PostgreSQL, files, Redis, or cache.

### 5. Fail-Fast Error Taxonomy (`src/security/errors.py`)
* **What it does:** Separates visitor key errors from owner infrastructure errors.
* **Our Rule:**
  * **Visitor Key Errors (401/403/429):** Fail instantly (`retryable = False`). Returns a friendly UI message: *"Your LlamaParse API key was rejected as invalid. Please check your credentials."* No retry loops.
  * **Owner Key Infrastructure Outages:** Controlled exponential backoff with circuit breakers.

### 6. Pre-flight Key Verification (`src/api/connections.py`)
* `verify_provider_connection()` sends lightweight, non-credit-consuming probe calls to confirm a visitor key is valid before any PDF parsing begins.

---

## 📑 Phase 2: Parser Layer, Universal Normalization & Quality Gate

> **Phase 2 Goal:** Transform raw PDFs from multiple parser technologies into a single normalized `StructuredDoc` format, clean visual artifacts, and audit parse fidelity with a pre-embedding Quality Gate.

```
[ Raw PDF File ]
       │
       ▼
[ Local Page Counter (local_pymupdf.py) ]
  Counts pages in 5ms for $0.00.
  Protects user from uploading 500 pages and burning credits.
       │
       ▼
[ Parser Layer (registry.py) ]
  • LocalPyMuPDFParser: Font-statistic heuristic parser (Free, $0)
  • LlamaParseAdapter: Markdown & pipe table parser (BYOK)
  • LandingAIAdapter: Spatial chunk & bounding box parser (BYOK)
       │
       ▼
[ Cleaning Engine (cleanup.py) ]
  • Fixes broken hyphenated words ("bil-\nlion" -> "billion")
  • Strips running headers ("Confidential") repeated across pages
  • Strips footers ("Page X of Y")
       │
       ▼
[ StructuredDoc Normalizer (structured_doc.py) ]
  Blocks: Headings (H1-H6), Paragraphs, Tables, List Items
       │
       ▼
[ Quality Gate (quality_gate.py) ]
  Compares parsed text against raw baseline.
  Coverage >= 65%? Headings exist? No garbled text?
```

### 1. Universal Document Schema (`src/ingest/parsers/structured_doc.py`)
Different parsers output completely different formats (LlamaParse outputs Markdown, Landing AI outputs JSON bounding boxes, PyMuPDF outputs span dictionaries). 

We translate all of them into a single typed contract:
```python
class Block(BaseModel):
    type: BlockType  # HEADING, PARAGRAPH, LIST_ITEM, TABLE, CODE, FIGURE, CAPTION
    text: str  # Cleaned text (tables formatted as Markdown)
    level: int | None  # 1..6 if heading, otherwise None
    page: int  # 1-indexed page number
    bbox: list[float]  # [top, left, bottom, right] coordinates (for citation highlighting)
    order: int  # Sequential reading order


class StructuredDoc(BaseModel):
    doc_id: str
    title: str
    page_count: int
    parser_used: str
    blocks: list[Block]
```
**Why this matters:** The downstream chunker (Phase 3) will only ever interact with `StructuredDoc`. It has zero dependency on any specific parser SDK.

### 2. The Cleaning Engine (`src/ingest/parsers/cleanup.py`)
Raw PDF text extraction introduces visual artifacts that poison vector search:
* **Hyphenation Repair (`fix_hyphenation`):**
  * When a word wraps across lines, it gets extracted as `"deci-\nsion"`. 
  * If a user searches for `"decision"`, standard keyword search fails.
  * Our cleaner automatically repairs this to `"decision"`.
* **Running Header & Footer Stripper (`remove_repeated_headers_and_footers`):**
  * In a 20-page report, the phrase `"Acme Corp - Confidential"` appears at the top of every single page.
  * If left alone, this phrase gets embedded 20 times, dominating vector similarity scores and pushing out real answers!
  * Our algorithm builds a frequency histogram of top/bottom lines across pages. If text appears across $\ge 40\%$ of pages, it is automatically purged as a running header or footer.
  * Page numbers like `"Page 3 of 20"` or `"- 4 -"` are stripped via regex.

### 3. Free Local Parser & 5ms Page Counter (`src/ingest/parsers/local_pymupdf.py`)
* **5ms Local Page Counter (`count_pages`):** Inspects the PDF header locally in 5ms for $0.00. If a user uploads a 500-page book, it rejects the file *before* sending it to cloud parsers, saving the user from burning 500 API credits!
* **Local Parsing Engine:** Calibrates document font statistics to infer heading levels (H1, H2, H3) based on relative font size and boldness.
* **Ground Truth Extraction (`extract_raw_reference_text`):** Provides a raw text baseline for the Quality Gate.

### 4. LlamaParse Cloud Adapter & Normalizer (`src/ingest/parsers/llamaparse.py`)
* Connects to LlamaIndex Cloud through the egress firewall using the visitor's `Secret` key.
* Translates Markdown headings (`#`), pipe tables (`|...|`), lists, and code fences into `StructuredDoc` blocks while maintaining page tracking.

### 5. Landing AI ADE Adapter with Spatial Grounding (`src/ingest/parsers/landingai.py`)
* Connects to Landing AI Agentic Document Extraction (`api.va.landing.ai`).
* Simultaneously extracts clean Markdown content and exact **grounding bounding boxes** (`chunk.grounding.box`), populating `Block.bbox` for visual citation highlighting.

### 6. Dynamic Parser Registry (`src/ingest/parsers/registry.py`)
* Provides a factory to look up and register parsers dynamically (`default_parser_registry.get("local_pymupdf")`, `"llamaparse"`, `"landingai"`).

### 7. The Quality Gate Inspector (`src/ingest/parsers/quality_gate.py`)
Prevents corrupted or silently dropped parser outputs from entering the vector index:

| Check | What It Looks For | Threshold / Failure Condition | Action Taken |
|---|---|---|---|
| **Text Coverage** | Ratio of parsed characters vs. raw text baseline | Warns if coverage is $< 65\%$ (content lost) or $> 250\%$ (text duplicated) | Flags `has_warnings = True` with exact coverage percentage. |
| **Heading Sanity** | Presence and hierarchy of document headings | Warns if doc has $\ge 4$ pages but **0 headings**, or if levels jump erratically (e.g., H1 $\to$ H5) | Advises user that section structure may be compromised. |
| **Empty Pages** | Pages that yielded 0 extracted blocks | Warns if $> 30\%$ of total pages produced zero blocks | Flags specific missing page numbers in metadata. |
| **Garbled Text** | Unicode replacement and unprintable symbols | Warns if $> 3\%$ of characters are `\ufffd` or unprintable | Flags encoding or OCR corruption. |

**Important Behavior:** The Quality Gate **never crashes the job**. It finishes processing, attaches a clear **Parse Quality Warning**, and advises the user: *"Parse quality warning: Low text coverage. Consider re-uploading with a different parser (e.g., Free Local Parser or LlamaParse)."*

---

## 🧩 Phase 3: Hybrid Chunker, Heading Fusion, Dual Embeddings & Qdrant Storage

> **Phase 3 Goal:** Transform `StructuredDoc` into structure-aware hierarchical chunks, enrich child chunks with heading fusion for maximum retrieval accuracy, vectorize with dual embeddings (Cohere Dense + local BM25 Sparse), and store in Qdrant and SQLite with strict session privacy (`scope`).

```
[ Normalized StructuredDoc ]
              │
              ▼
┌───────────────────────────────┐
│ 1. Heading Breadcrumbs Stack  │  Doc > H1 > H2 > H3
└─────────────┬─────────────────┘
              │
              ▼
┌───────────────────────────────┐
│ 2. Parent-Child Decomposition │  Parents: ~1000 tokens (saved in SQLite)
└─────────────┬─────────────────┘  Children: ~300 tokens (indexed in Qdrant)
              │
              ▼
┌───────────────────────────────┐
│ 3. Heading Fusion             │  display_text: clean paragraph
└─────────────┬─────────────────┘  embedding_text: [Breadcrumbs] + paragraph
              │
              ▼
┌───────────────────────────────┐
│ 4. Dual Vectorization         │  • Dense: Cohere Embed v3 (1024-dim, owner key)
└─────────────┬─────────────────┘  • Sparse: Local BM25 (in-process, $0.00 cost)
              │
              ▼
┌───────────────────────────────┐
│ 5. Dual Storage Isolation     │  • Qdrant: points tagged with scope="session_xyz"
└───────────────────────────────┘  • SQLite: parents filtered by parent_id & scope
```

### 1. Hybrid Chunker (`src/ingest/chunking/hybrid_chunker.py`)
* **Hierarchical Breadcrumbs (`heading_stack.py`):** Sequential structure pass that tags every paragraph, table, and list item with its ancestral section path (e.g. `Acme Report > Financials > 2026 Revenue`).
* **Table Row Preservation (`table_splitter.py`):** Tables are kept atomic if under 800 tokens. Oversized tables are split strictly by rows, repeating the Markdown header on every chunk so columns never lose context.
* **Recursive Token Splitter (`recursive_splitter.py`):** Separator cascade (`\n\n` $\to$ `\n` $\to$ `. , ? , ! ` $\to$ ` `) with configurable token overlap (12%).
* **Deterministic Chunk IDs:** Every parent and child chunk gets an idempotent SHA-256 hash ID (`c_<hash>`), preventing vector duplication upon job retries.
* **Sequential Chunk Linking:** Sets `prev_chunk_id` and `next_chunk_id` on all children for window expansion in Phase 4.

### 2. Heading Fusion
Every child chunk generates two distinct text representations:
* `display_text`: The clean, unpolluted original passage shown to the visitor and passed to the LLM during answer synthesis.
* `embedding_text`: `[Breadcrumbs]\n\nClean text`. This injects section context into Cohere vector search even if the child passage doesn't mention the document or section title directly!

### 3. Dual Embedding Layer (Dense + Sparse Hybrid)
* **Cohere Embed Adapter (`src/retrieval/embed.py`):**
  * Pinned model `embed-english-v3.0` (1024 dimensions).
  * Strict separation between `input_type = "search_document"` (indexing) and `search_query` (retrieval).
  * Batching up to 96 items with bounded exponential backoff for rate limits.
  * Usage meter callback hook to track chunk embeddings against owner spend caps.
* **Local Sparse Vectorizer (`src/retrieval/sparse.py`):**
  * In-process term frequency / BM25 weighting with deterministic token hashing into a 1M dimension space.
  * Zero external API cost ($0.00). Catches exact part numbers, dollar figures, and acronyms that dense vectors blur.

### 4. Qdrant Vector Store with Scope Isolation (`src/retrieval/store.py`)
* Dual vector collection setup in Qdrant: `"dense"` (Cosine, 1024-dim) and `"sparse"` (BM25 values).
* Payload indexes on `scope` and `doc_id`.
* Server-enforced scope filtering: Searches strictly filter `scope IN [session_id, "demo"]`. User A can **never** search or view User B's documents.
* Clean TTL and session deletion via `delete_by_scope` and `delete_by_doc`.

### 5. Relational SQLite Storage & Zero-Key Audit (`src/storage/db.py`)
* Manages structured relational tables: `sessions`, `jobs`, `documents`, `parents`, `parse_cache`, and `usage_daily`.
* **Zero-Secret Invariant:** Validated by automated security audit test that guarantees no table or column ever stores credentials or API keys.
* Parent context fetching is strictly scoped: `SELECT ... WHERE parent_id = ? AND (session_id = ? OR session_id = 'demo')`.

### 6. Offline Demo Ingestion Script (`scripts/ingest_demo.py`)
* Pipeline script to parse, clean, audit, chunk, embed, and index public documents from `demo_corpus/` into Qdrant under `scope = "demo"` for Tier A instant demo access.

---

## 🎯 Phase 4: Hybrid Retrieval, Cohere Rerank, Generation & Interactive CLI

> **Phase 4 Goal:** Transform raw vectors and SQLite parents into cited, trustworthy answers from the terminal: query embedding $\to$ hybrid search $\to$ Cohere Rerank $\to$ not-found gate $\to$ context expansion $\to$ streaming LLM $\to$ citation audit.

```
[ User Query / CLI ]
        │
        ▼
┌────────────────────────────────┐
│ 1. Question Validation & Gate  │  Length caps (<1,000 chars) & prompt injection screen
└───────────────┬────────────────┘
        │
        ▼
┌────────────────────────────────┐
│ 2. Conditional Query Rewrite   │  Multi-turn only: transforms "What did they report?"
└───────────────┬────────────────┘  into standalone questions ($0 cost on turn 1)
        │
        ▼
┌────────────────────────────────┐
│ 3. Hybrid Search in Qdrant     │  Dense (Cohere search_query) + Sparse (in-process BM25)
└───────────────┬────────────────┘  Mandatory Server Scope Filter: [session_id, "demo"]
        │
        ▼
┌────────────────────────────────┐
│ 4. Cohere Rerank v3.5 (Top 5)  │  Two-stage neural reranking behind IReranker contract
└───────────────┬────────────────┘  Bounded retries, circuit breaker & hybrid fallback
        │
        ▼
┌────────────────────────────────┐
│ 5. Not-Found Gate              │  Best score < 0.25? STOP! Exit early with $0 LLM cost.
└───────────────┬────────────────┘
        │ (Score >= 0.25)
        ▼
┌────────────────────────────────┐
│ 6. Parent Context Expansion    │  Parent <= 1,200 tokens? Use full section from SQLite!
└───────────────┬────────────────┘  Deduplicates passages & caps context to 3,500 tokens
        │
        ▼
┌────────────────────────────────┐
│ 7. Untrusted Context Prompt    │  Passages numbered [1], [2] & labeled UNTRUSTED DATA
└───────────────┬────────────────┘  Strict provenance instructions: "Answer only from context"
        │
        ▼
┌────────────────────────────────┐
│ 8. Streaming LLM Generation    │  Owner Default (Groq) or Visitor BYOK (OpenAI/Anthropic)
└───────────────┬────────────────┘  Tokens streamed in real-time to stdout
        │
        ▼
┌────────────────────────────────┐
│ 9. Citation & Grounding Audit  │  Validates cited IDs against context, catches hallucinations,
└────────────────────────────────┘  and enriches output with document title, page & breadcrumb!
```

### 1. Hybrid Search with Mandatory Scope Filter (`src/retrieval/search.py`)
* **How it works:** When a visitor asks a question, we compute:
  1. A dense query embedding using **Cohere Embed** (`input_type="search_query"`).
  2. A sparse keyword vector locally via **BM25** ($0 external cost).
* **Scope Isolation:** Searches in Qdrant are locked to `scope IN [session_id, "demo"]`. The client cannot pass arbitrary filters. A visitor in private session `session_abc` can only search their own uploaded documents and the public demo corpus.
* **Reciprocal Rank Fusion (RRF):** Merges dense semantic hits with exact keyword matches to retrieve the top 30-50 child chunks.

### 2. Cohere Rerank Adapter & Circuit Breaker (`src/retrieval/rerank.py`)
* **Why rerank?** Dense vector search often brings back distantly relevant chunks. **Cohere Rerank v3.5** scores cross-attention between the query and candidates, re-ordering the top 5 most relevant passages.
* **Resilience & Fallback:**
  * Uses a short timeout (5.0s) with 1 transient retry.
  * **Circuit Breaker:** If Cohere experiences repeated upstream errors (5 consecutive failures), the circuit breaker opens for 60s to prevent hanging requests.
  * **Graceful Degradation:** If reranking fails, the pipeline automatically falls back to raw hybrid-search order and sets `is_fallback: True` without crashing.
* **Owner Spend Tracking:** Invokes a usage callback on every successful call to decrement the session's rerank quota.

### 3. The "Not-Found" Cost Guard (`src/retrieval/search.py`)
* **The Problem:** In typical RAG systems, if someone asks `"What are the sales figures for Mars rover titanium wheels?"` over a company financial report, the system still retrieves low-scoring noise, calls GPT-4, and burns expensive tokens just to hear the model say *"I don't know"*.
* **Our Solution:** If the best candidate's rerank score is below `0.25`, the pipeline **exits immediately before calling the LLM**.
* **Financial Result:** **$0 spent on generation** for unanswerable questions.

### 4. Parent / Window Context Expansion (`src/retrieval/expansion.py`)
* **The Dilemma:** Small chunks (300 tokens) are best for vector search accuracy, but LLMs need broad context (1,000+ tokens) to generate coherent, complete answers.
* **The Solution:**
  1. The child chunk points to its `parent_id`.
  2. We fetch the parent section from SQLite strictly by `parent_id` AND `scope`.
  3. If `parent_tokens <= 1,200`, we inject the **entire parent section** into the prompt.
  4. If multiple retrieved child chunks belong to the same section, we **deduplicate** so the parent passage appears only once.
  5. The entire context is bounded to a strict **3,500 token budget** to prevent exceeding model limits.

### 5. Untrusted Context Boundaries (`src/generation/prompt.py`)
* **Prompt Injection Defense:** Reference documents are delimited inside explicit boundaries:
  ```text
  --- BEGIN UNTRUSTED REFERENCE CONTEXT ---
  [1] Source: Annual Report | Page: 2 | Section: Financial Performance
  """
  ...passage text...
  """
  --- END UNTRUSTED REFERENCE CONTEXT ---
  ```
* The system prompt explicitly commands the model to treat all reference context as **untrusted data** and never execute instructions found inside documents.

### 6. Streaming LLM Adapters (`src/generation/llm.py`)
* **Owner Default Adapter (`GroqLLM`):** High-speed inference using `openai/gpt-oss-120b` or Llama 3 models with capped output tokens (`max_tokens=1024`).
* **Visitor BYOK Adapters (`OpenAILLM` & `AnthropicLLM`):** Support visitor-supplied keys for GPT-4o-mini and Claude 3.5 Haiku. Fail-fast with zero retries on visitor authentication errors.
* **Egress Protected:** All LLM adapters communicate exclusively through `SecureHttpClient`, guaranteeing that requests cannot be redirected or manipulated.

### 7. Citation Audit & Hallucination Detector (`src/generation/citations.py`)
* **How it works:** The LLM is instructed to cite source passages using bracket notation (`[1]`, `[2]`).
* **The Audit:**
  * Checks every bracket number against the actual passages provided in the prompt.
  * If the model hallucinates a non-existent citation (e.g. `[5]` when only 2 passages were provided), it flags `invalid_citations: [5]` and marks `is_grounded: False`.
  * For every verified citation, it attaches full provenance metadata: **Document Title**, **Page Number**, **Section Breadcrumb**, and a **Verified Text Snippet**.

### 8. Conditional Query Rewriter (`src/generation/rewrite.py`)
* **Turn 1:** `history is None` $\to$ Bypasses rewriting completely ($0 cost).
* **Turn 2+:** If a follow-up question contains ambiguous pronouns (e.g. `"What did they report for operating expenses?"`), a cheap rewrite call de-references the question into `"What were Acme Corporation's operating expenses in FY2025?"` before retrieval runs.

---

### 💻 Interactive CLI Demonstration (`src/cli.py`)

You can run and test the complete Phase 4 pipeline directly from your terminal!

#### Example 1: Direct Fact Lookup with Verified Provenance
```powershell
python -m src.cli ask "What is Acme Corporation's debt-to-equity ratio?"
```
**Terminal Output:**
```text
[Provenance RAG] Scope: demo | Query: What is Acme Corporation's debt-to-equity ratio?

Acme Corporation’s debt‑to‑equity ratio is **0.42** [1].

============================================================
VERIFIED SOURCES & PROVENANCE:
============================================================
 [1] Acme Annual Financial Report 2025 (Page 2) > Acme Annual Financial Report 2025 > Financial Performance & Balance Sheet
     "Financial Performance & Balance Sheet

Revenue Breakdown:
- Enterprise Cloud: ,000,000 (62%)
- Professional Services: ,0..."

------------------------------------------------------------
Timing Breakdown: {'rewrite_ms': 0.0, 'retrieval_ms': 3666.9, 'expansion_ms': 4.0, 'generation_ms': 682.2, 'citation_audit_ms': 0.0, 'total_ms': 4684.7}
Grounded: True | Found: True
============================================================
```

#### Example 2: Constitutional Rights with Section Breadcrumbs
```powershell
python -m src.cli ask "Which freedoms are explicitly protected under the First Amendment?"
```
**Terminal Output:**
```text
[Provenance RAG] Scope: demo | Query: Which freedoms are explicitly protected under the First Amendment?

The First Amendment explicitly protects the following freedoms:
- Freedom of religion (establishment and free exercise)
- Freedom of speech
- Freedom of the press
- The right to peaceably assemble
- The right to petition the Government for a redress of grievances [1].

============================================================
VERIFIED SOURCES & PROVENANCE:
============================================================
 [1] Us Constitution Bill Of Rights (Page 2) > Us Constitution Bill Of Rights > The Bill of Rights - Amendments
     "The Bill of Rights - Amendments

Amendment I: Congress shall make no law respecting an establishment of religion, or pro..."

------------------------------------------------------------
Timing Breakdown: {'rewrite_ms': 0.0, 'retrieval_ms': 4267.3, 'expansion_ms': 5.0, 'generation_ms': 1219.6, 'citation_audit_ms': 0.0, 'total_ms': 5828.0}
Grounded: True | Found: True
============================================================
```

#### Example 3: Not-Found Gate in Action ($0 Spent on LLM)
```powershell
python -m src.cli ask "What were the sales figures for Mars rover titanium wheels?"
```
**Terminal Output:**
```text
[Provenance RAG] Scope: demo | Query: What were the sales figures for Mars rover titanium wheels?

I could not find the answer in the provided documents.

============================================================
VERIFIED SOURCES & PROVENANCE:
============================================================
 No source passages cited.
------------------------------------------------------------
Timing Breakdown: {'rewrite_ms': 0.0, 'retrieval_ms': 4248.8, 'total_ms': 4574.5}
Grounded: False | Found: False
============================================================
```
*(Notice: `generation_ms` is 0.0! The system rejected the unanswerable query at the retrieval stage, completely protecting your wallet).*

#### Example 4: Reranking Ablation Testing
```powershell
python -m src.cli ask "What is Acme Corporation's debt-to-equity ratio?" --disable-rerank
```
Bypasses Cohere Rerank to test raw dense+sparse hybrid retrieval order against the neural reranker.

---

## 🌐 Phase 5: REST API, Sessions, Demo Mode & Owner Cost Controls

> **Phase 5 Goal:** Expose the complete RAG pipeline as a production-grade, secure REST API (FastAPI) where anyone can chat on the demo corpus with zero API keys (Tier A), with rigorous server-derived scope isolation, atomic per-session spend caps, per-IP rate limiting, dynamic kill switches, and non-content privacy logging.

### 1. Server-Derived Scope & Multi-Tenant Session Isolation (`src/api/sessions.py`)
In public multi-tenant RAG applications, **clients must never specify or influence their search scope**. 
* **Session Issuance (`POST /session`):** Generates a 32-byte cryptographically random hex token with an explicit TTL (`expires_at`), stored in SQLite.
* **Server-Controlled Scope:** The `get_current_session` FastAPI dependency maps the session token to either `scope = "demo"` (Tier A) or `scope = session_id` (Tiers B & C). Any user-supplied filters or scopes are strictly discarded.
* **Cross-Session Privacy:** Multi-tenant isolation tests prove that Session A can never retrieve documents, chunks, or parent passages indexed by Session B, even if knowing the document ID.

### 2. 7-Gate Security & Cost Guard Sequence (`src/api/chat.py`)
Every question sent to `POST /chat` passes through seven defensive gates **before any paid API call** is executed:

```
[ POST /chat Request ]
        │
        ▼
1. Input Screen Gate      ──▶ Max length (1,000 chars) & prompt injection screening
        │
        ▼
2. IP Rate-Limit Gate     ──▶ In-memory sliding window (10 req/min) & daily IP limit
        │
        ▼
3. Kill Switch Gate       ──▶ Immediate owner block (KILL_SWITCH_DISABLE_OWNER_LLM)
        │
        ▼
4. Session Cap Gate       ──▶ Atomic SQLite counter check (Max 15 owner questions)
        │
        ▼
5. Rerank Quota Gate      ──▶ Session rerank cap check (Max 30 calls)
        │
        ▼
6. Not-Found Gate         ──▶ Cohere rerank score < 0.25? Refuse early ($0 LLM spent)
        │
        ▼
7. Output Token Cap Gate  ──▶ Owner LLM capped to 1,024 max output tokens
        │
        ▼
[ Verified Answer + Provenance Sources ]
```

### 3. Owner Cost Caps, "Demo at Capacity" & Kill Switch (`src/api/caps.py`)
* **Atomic Counter Increments:** SQLite transactions update question, rerank, and chunk counters atomically to prevent race conditions from concurrent browser tabs.
* **Global Daily Budgets (`usage_daily`):** Tracks total daily spend across all users. If owner daily limits are reached, the system flips to **"Demo at capacity"** mode (returns a friendly capacity message without calling paid models).
* **Dynamic Kill Switch:** Instant blocking for owner LLM or document uploads via `.env` or runtime flags without redeploying code.
* **Scope Mutation Guard:** Prevents any visitor session from modifying or writing chunks into the pre-indexed `demo` scope.

### 4. Privacy-Safe Structured Logging (`src/api/logging.py`)
* **Strict Non-Content Logging:** Logs only operational metadata (`request_id`, `tier`, `duration_ms`, `tokens_used`, string lengths).
* **Zero Content Leakage:** Question text, answer text, and document snippets are **never written to disk or application logs**.
* **Automatic Key Redaction:** Regular expressions detect and mask accidental provider API key strings in log strings.

### 5. API Endpoints Reference

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | None | Liveness probe for load balancers & uptime monitors (`status: ok`) |
| `GET` | `/examples` | None | Clickable demo question chips for Tier A (zero setup) |
| `POST` | `/session` | None | Issues a secure session token & server-derived scope |
| `GET` | `/usage` | Bearer Token | Live remaining allowance for the frontend meter |
| `POST` | `/connections/test` | None | Tests visitor-supplied API keys in RAM (never stored) |
| `POST` | `/chat` | Bearer Token | Runs the 7-gate RAG pipeline with verified source cards |

---

### 🧪 How to Test Phase 5 API Endpoints

#### 1. Start the API Server
```powershell
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```
Interactive Swagger documentation is available at: **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

#### 2. Run Automated Test Suite (60 Tests)
```powershell
python -m pytest tests/api/ -v
```

#### 3. Step-by-Step Testing Commands

##### Step A: System Health Probe
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method GET
```
**Output:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

##### Step B: Fetch Example Question Chips (No Auth Required)
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/examples" -Method GET
```
**Output:**
```json
{
  "examples": [
    {
      "id": "ex_1",
      "question": "What is Provenance RAG and how does it cite its sources?",
      "category": "overview"
    },
    {
      "id": "ex_2",
      "question": "How does the hybrid chunking algorithm combine recursive splitting with parent-child chunks?",
      "category": "technical"
    }
  ]
}
```

##### Step C: Start a Visitor Session
```powershell
$session = Invoke-RestMethod -Uri "http://127.0.0.1:8000/session" -Method POST
$token = $session.session_id
Write-Host "Created Session: $token | Scope: $($session.scope)"
```
**Output:**
```json
{
  "session_id": "e4b6c31828f7481ba921e3f2aa61198e",
  "tier": "tier_a",
  "scope": "demo",
  "expires_at": "2026-10-27T10:00:00Z"
}
```

##### Step D: Inspect Live Usage Meter
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/usage" `
  -Method GET `
  -Headers @{ "Authorization" = "Bearer $token" }
```
**Output:**
```json
{
  "session_id": "e4b6c31828f7481ba921e3f2aa61198e",
  "tier": "tier_a",
  "questions_used": 0,
  "questions_remaining": 15,
  "documents_uploaded": 0,
  "documents_remaining": 3,
  "chunks_embedded": 0,
  "chunks_remaining": 50,
  "owner_llm_capped": false,
  "demo_at_capacity": false,
  "resets_at": "2026-10-27T00:00:00Z"
}
```

##### Step E: Test a Visitor API Key Safely ($0 Cost, Never Stored)
```powershell
$testKeyBody = @{ provider = "openai"; key = "sk-test-fakekey" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/connections/test" `
  -Method POST `
  -ContentType "application/json" `
  -Body $testKeyBody
```
**Output:**
```json
{
  "provider": "openai",
  "status": "invalid_key",
  "message": "Invalid API key provided for openai."
}
```

##### Step F: Ask a Question via RAG Pipeline
```powershell
$chatBody = @{
  question = "What is Provenance RAG and how does it cite its sources?"
  history = @()
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/chat" `
  -Method POST `
  -Headers @{ "Authorization" = "Bearer $token" } `
  -ContentType "application/json" `
  -Body $chatBody
```
**Output:**
```json
{
  "answer": "Provenance RAG is a hybrid retrieval-augmented generation framework that grounds responses in structured documents and audits every cited passage [1].",
  "sources": [
    {
      "source_id": "1",
      "breadcrumb": "Architecture > Overview",
      "page_number": 1,
      "snippet": "Provenance RAG links every claim to source parent sections.",
      "score": 0.94
    }
  ],
  "not_found": false,
  "tier": "tier_a",
  "duration_ms": 420.5,
  "tokens_used": 185
}
```

---

## 📤 Phase 6: Upload Flow, Asynchronous Jobs & Data Lifecycle

Phase 6 implements the complete Tier B and Tier C document upload pipeline, background asynchronous job runner, quality gate evaluation, automatic local fallback, session parse cache, and leak-proof data cleanup:

### 1. Pre-flight Validation & Chunk Estimation (`POST /upload/validate`)
* **Magic-bytes validation:** Enforces `%PDF-` signature; immediately rejects disguised non-PDF binaries (`400 Bad Request`).
* **Size Cap:** Enforces hard 10MB limit per uploaded file (`413 Content Too Large`).
* **Encryption Check:** Rejects encrypted or password-protected PDFs (`422 Unprocessable Entity`) before any parsing resources are wasted.
* **Fast Page Count:** Uses PyMuPDF's low-level header inspection (4ms) to count pages.
* **Session Quotas:** Verifies document page limits (max 30 pages/doc), session document counts (max 5 docs), and total session page limits (max 50 pages).
* **Chunk & Allowance Estimation:** Previews expected chunk counts and session quota consumption before committing.

### 2. Asynchronous Ingestion Job Runner (`src/api/jobs.py` & `POST /upload`, `GET /jobs/{id}`)
* **Non-Blocking Background Worker:** `POST /upload` validates the file, registers a job in SQLite, and immediately returns `202 Accepted` with a `job_id`.
* **Predictable State Machine:** Transitions cleanly through `queued` $\to$ `parsing` $\to$ `chunking` $\to$ `embedding` $\to$ `indexing` $\to$ `ready` (or `failed`).
* **Ephemeral Visitor Parser Key Lifecycle:** If a visitor supplies an optional parser key (e.g. for LlamaParse), the secret is kept in memory solely for that job and **guaranteed to be shredded in a `finally` block**—it is never written to SQLite, logs, or disk.
* **Pre-Embedding Quality Gate:** Evaluates text coverage, heading sanity, and garbled symbols. Non-blocking warnings are recorded on the job without crashing the pipeline.
* **Automatic Local Fallback:** If a visitor cloud parser fails (network timeout, rate limit, invalid key), the runner gracefully re-parses using `local_pymupdf` ($0 cost), ensuring the user still gets a searchable document.

### 3. Session-Scoped Parse Cache
* Caches raw parse trees in SQLite keyed strictly by `(session_id, content_hash, parser, parser_version)`.
* Completely free of API keys or credentials; cannot be accessed across different sessions.

### 4. Data Lifecycle & "Delete My Data" (`DELETE /session`, TTL Cleaner)
* **Instant Hard Wipe (`DELETE /session`):** Requires zero visitor keys. Immediately deletes all vector embeddings in Qdrant matching `scope == session_id`, wipes all SQLite session rows, parents, documents, jobs, and cached parse trees.
* **Single Document Deletion (`DELETE /session/documents/{doc_id}`):** Deletes document vectors and parent blocks while recalculating session usage.
* **Background TTL Cleaner:** An async task runs every 5 minutes purging expired sessions automatically.

---

## 📊 Phase 7: Evaluation, Tuning & Privacy-Safe Tracing

Phase 7 delivers empirical proof of quality, statistical calibration for retrieval thresholds, financial cost protection, and privacy-preserving observability:

### 1. Curated Golden Benchmark Set (`eval/golden_set.jsonl`)
A 50-question benchmark frozen across four distinct evaluation categories:
* **15 Direct Fact Lookups:** Exact single-passage information retrieval (e.g., Acme consolidated revenue, executive roles).
* **10 Table & Numerical Queries:** Precision metrics and balance sheet lookups requiring exact table cell extraction.
* **10 Multi-Section Synthesis:** Cross-page structural queries spanning executive summaries, risks, and financial statements.
* **15 Not-in-Corpus Trick Queries:** Out-of-distribution queries (e.g., Martian mining dividends, lunar taxes) designed to test false-positive resistance.

### 2. Core Evaluation Engine (`eval/evaluate.py`)
Automated measurement harness evaluating the full RAG pipeline:
* **Retrieval Performance:** Computes **Recall@5**, **Recall@10**, and **Mean Reciprocal Rank (MRR)**.
* **Faithfulness & Grounding:** Assesses factual consistency against retrieved context passages.
* **Cost Safety Gate:** Evaluates **Not-Found Accuracy (100%)** on unanswerable trick queries.
* **Latency & Spend Metrics:** Measures p50/p95 latency, Cohere API calls, and LLM token expenditures per query.
* **Automated Reporting:** Generates publication-ready `eval/results/summary.md` and `eval/results/metrics.json`.

### 3. 5-Way Architectural Ablation Benchmark (`eval/ablation.py`)
Rigorous comparative ablation measuring the isolated impact of each pipeline component:

| # | Configuration | Recall@5 | Recall@10 | MRR | Faithfulness | Not-Found Acc | Latency (p95) |
|---|---|---|---|---|---|---|---|
| 1 | **Dense Vector Search Only (Cohere v3, No Rerank)** | `51.43%` | `51.43%` | `0.514` | `88.5%` | `100.0%` | `120ms` |
| 2 | **Sparse BM25 Search Only (Local BM25, No Rerank)** | `48.20%` | `54.10%` | `0.482` | `84.0%` | `100.0%` | `35ms` |
| 3 | **Hybrid Search (Dense + BM25, No Rerank)** | `68.50%` | `75.20%` | `0.685` | `89.2%` | `100.0%` | `135ms` |
| 4 | **Hybrid Search + Heading Breadcrumb Fusion** | `78.10%` | `84.30%` | `0.774` | `91.0%` | `100.0%` | `140ms` |
| 5 | **Full Production (Hybrid + Heading Fusion + Cohere Rerank v3.5 + Parent Expansion)** | **`88.60%`** | **`94.20%`** | **`0.852`** | **`94.5%`** | **`100.0%`** | `295ms` |

> **Senior Takeaway:** Cohere Rerank v3.5 delivers the single largest leap in MRR (+0.167), while Heading Breadcrumb Fusion prevents cross-section collisions and Parent Context delivers the complete narrative surrounding paragraphs.

### 4. Threshold & Spend Calibration (`eval/tune_thresholds.py`)
* **Not-Found Gate Cutoff:** Score distribution analysis places the optimal reranker rejection threshold at `0.25 - 0.35`, successfully intercepting trick queries with $0 LLM spend.
* **Empirical Cost per Query:** Measured at **$0.00012 - $0.0023 USD** per completed query.
* **Production Caps:** Validates Tier A (15 questions max ~$0.035/session), Tier B (30 questions max ~$0.070/session), and a $2.50/day owner safety budget supporting ~1,000 queries/day.

### 5. Access Tier & Key Boundary Verifier (`eval/tier_checks.py`)
Scripted verification harness ensuring:
* **Tier A:** Zero keys, read-only demo corpus, owner payment bounded by atomic session caps.
* **Tier B:** Private session scope, ephemeral parser keys never stored in SQLite.
* **Tier C:** Visitor LLM keys are held in memory only, never written to disk or logs, and do not consume owner LLM budget.

### 6. Privacy-Safe Tracing Engine (`src/security/tracing.py`)
Context-managed distributed tracing engine with dual privacy guarantees:
* **Demo Scope (`scope = "demo"`):** Retains full query content and passage snippets for debugging and offline evaluations.
* **Visitor Scope (`scope != "demo"`):** Strictly enforces `PrivacyLevel.METADATA_ONLY`, masking all user questions, generated text, and document contents with `[REDACTED_VISITOR_CONTENT]`.

---

## 🔍 Real-World Walkthrough: Trace of an Uploaded Document


Here is a step-by-step trace of how a real document is processed from start to finish:

### The Input Document: `Company_Annual_Report.pdf` (3 Pages)
* **Page 1:**
  * Top: `"Acme Corp Internal Report"`
  * Title: `"Global Operations 2026"` (Font size: 24pt)
  * Subheading: `"Executive Summary"` (Font size: 16pt)
  * Body: `"Operating income reached $4.2 bil-\nlion, representing steady expan-\nsion."`
  * Bottom: `"Page 1 of 3"`
* **Page 2:**
  * Top: `"Acme Corp Internal Report"`
  * Subheading: `"Regional Breakdown"` (Font size: 16pt)
  * Table:
    ```
    | Region | Growth |
    | North America | 12% |
    | Europe | 8% |
    ```
  * Bottom: `"Page 2 of 3"`
* **Page 3:**
  * Top: `"Acme Corp Internal Report"`
  * Subheading: `"Strategic Outlook"` (Font size: 16pt)
  * Body: `"Continued investment into RAG architectures."`
  * Bottom: `"Page 3 of 3"`

---

### Step 1: Local Page Count & Pre-flight Check (Phase 2)
* `count_pages()` runs in 4ms: `page_count = 3`.
* Confirms within per-session limit of 30 pages.

### Step 2: Parsing (e.g., Free Local Parser) (Phase 2)
* `LocalPyMuPDFParser` evaluates all text spans:
  * Median font size = 10.5 pt.
  * Size 24 pt $\to$ Promoted to **Heading Level 1 (H1)**.
  * Size 16 pt $\to$ Promoted to **Heading Level 2 (H2)**.
  * Body spans $\to$ Categorized as Paragraphs.

### Step 3: Cleaning Engine (Phase 2)
* Hyphenation repaired:
  * `"bil-\nlion"` $\to$ `"billion"`
  * `"expan-\nsion"` $\to$ `"expansion"`
* Running header detected:
  * `"Acme Corp Internal Report"` appears on pages 1, 2, and 3 ($\ge 40\%$ frequency).
  * **Result: Stripped from all pages.**
* Running footer detected:
  * `"Page X of 3"` matched page number regex.
  * **Result: Stripped from all pages.**

### Step 4: Normalization into StructuredDoc (Phase 2)
The clean document now looks like this:
```json
{
  "doc_id": "doc_f839a012b4e8",
  "title": "Company Annual Report",
  "page_count": 3,
  "parser_used": "local_pymupdf",
  "blocks": [
    { "order": 0, "type": "heading",   "level": 1, "page": 1, "text": "Global Operations 2026" },
    { "order": 1, "type": "heading",   "level": 2, "page": 1, "text": "Executive Summary" },
    { "order": 2, "type": "paragraph", "level": null, "page": 1, "text": "Operating income reached $4.2 billion, representing steady expansion." },
    { "order": 3, "type": "heading",   "level": 2, "page": 2, "text": "Regional Breakdown" },
    { "order": 4, "type": "table",     "level": null, "page": 2, "text": "| Region | Growth |\n| North America | 12% |\n| Europe | 8% |" },
    { "order": 5, "type": "heading",   "level": 2, "page": 3, "text": "Strategic Outlook" },
    { "order": 6, "type": "paragraph", "level": null, "page": 3, "text": "Continued investment into RAG architectures." }
  ]
}
```

### Step 5: Quality Gate Evaluation (Phase 2)
* Text Coverage: 98.7% extracted $\to$ **PASS**
* Heading Sanity: 4 headings found across 3 pages, logical structure $\to$ **PASS**
* Empty Pages: 0 missing pages $\to$ **PASS**
* Garbled Characters: 0.00% $\to$ **PASS**
* **Result:** `QualityGateResult(passed=True, has_warnings=False)`.

### Step 6: Chunking, Heading Fusion & Dual Indexing (Phase 3)
* **Parent Chunk Created:** Full section text stored in SQLite under `parent_id = "p_a912"`.
* **Child Chunk Created:** Small passage `"Operating income reached $4.2 billion..."` with `prev_chunk_id = None`, `next_chunk_id = "c_b341"`.
* **Heading Fusion:** `embedding_text` generated as `"[Global Operations 2026 > Executive Summary]\n\nOperating income reached $4.2 billion..."`.
* **Vector Embeddings:** 1024-dim dense vector computed via Cohere + sparse BM25 vector computed locally.
* **Qdrant Storage:** Upserted with `scope = "session_user123"`.

### Step 7: Asking a Question & Retrieval (Phase 4)
* The visitor asks: `"What was the operating income for Global Operations?"`
* The server locks search to `scope = "session_user123"`.
* A query vector is generated with Cohere Embed (`search_query` type) and a sparse BM25 keyword query.
* Qdrant hybrid search finds child chunk `c_b341` (`score = 0.89`).

### Step 8: Cohere Reranking & Not-Found Gate (Phase 4)
* **Cohere Rerank v3.5** evaluates relevance: `score = 0.94`.
* Since `0.94 >= 0.25`, the not-found gate passes immediately.

### Step 9: Context Expansion (Phase 4)
* Child chunk `c_b341` references `parent_id = "p_a912"`.
* Parent size is 145 tokens (well within the 1,200 token parent cap).
* SQLite retrieves the entire parent section text:
  `"Executive Summary\nOperating income reached $4.2 billion, representing steady expansion."`

### Step 10: Answer Generation & Citation Audit (Phase 4)
* The prompt is built with delimited untrusted context:
  `[1] Source: Company Annual Report | Page: 1 | Section: Global Operations 2026 > Executive Summary`
* The model streams the answer:
  `"Operating income reached $4.2 billion [1]."`
* The citation auditor verifies `[1]` points to passage 1 $\to$ `is_grounded: True`.
* The user receives the answer with verified document title, page number, and section trail!

---

## 🗺️ Codebase Directory Map (Organized by Phase)

```text
provenance-rag/
├── README.md                      # Comprehensive system guide & documentation
├── pyproject.toml                 # [Phase 0] Dependencies, build tooling, ruff, & pytest config
├── .gitignore                     # [Phase 0] Protection for .env, virtualenvs, uploads, & caches
├── .env.example                   # [Phase 0] Owner configuration template & spend controls
├── .github/
│   └── workflows/
│       └── ci.yml                 # [Phase 0] GitHub Actions automated lint & pytest CI pipeline
├── docs/
│   └── DECISIONS.md               # [Phase 0] Architecture Decision Records (ADRs)
├── demo_corpus/                   # [Phase 0] Public documents for Tier A (zero-key demo)
├── samples/                       # [Phase 0] Sample PDFs for testing and quality gate benchmarks
├── scripts/
│   ├── create_demo_pdfs.py        # [Phase 7] High-fidelity PDF generator with tables & exact numbers
│   ├── ingest_demo.py             # [Phase 3] Offline demo corpus ingestion script (scope="demo")
│   ├── reembed_demo.py            # [Phase 3] Demo corpus re-embedding utility
│   └── run_eval.py                # [Phase 7] End-to-end evaluation, ablation, and calibration runner
│
├── eval/                          # [Phase 7] Benchmark Evaluation & Tuning Engine
│   ├── golden_set.jsonl           # [Phase 7] 50 curated benchmark questions across 4 categories
│   ├── models.py                  # [Phase 7] Pydantic models for evaluation queries, metrics & ablations
│   ├── evaluate.py                # [Phase 7] Recall@5/10, MRR, Faithfulness, latency & cost engine
│   ├── ablation.py                # [Phase 7] 5-way architectural ablation experiment runner
│   ├── tune_thresholds.py         # [Phase 7] Not-found threshold and empirical cost budget calibrator
│   ├── tier_checks.py             # [Phase 7] Automated Tier A, B, and C boundary & isolation verifier
│   └── results/                   # [Phase 7] Generated publication-ready reports & ablation tables
│       ├── summary.md             # [Phase 7] Markdown evaluation executive summary
│       ├── metrics.json           # [Phase 7] Machine-readable metrics payload
│       ├── ablation.md            # [Phase 7] 5-way ablation comparison table & senior takeaways
│       └── thresholds_and_caps.md # [Phase 7] Calibrated score cutoffs & financial spend cap recommendations
│
├── src/
│   ├── interfaces.py              # [Phase 0] Blueprints: IParser, IChunker, IEmbedder, IReranker, ILLM
│   │
│   ├── security/                  # [Phase 1 & 7] The Security Moat & Privacy Tracing
│   │   ├── secret.py              # [Phase 1] Secret wrapper class (str/repr/json -> '***')
│   │   ├── redaction.py           # [Phase 1] Regex logging filter & dictionary credential scrubber
│   │   ├── egress.py              # [Phase 1] Outbound domain allowlist (SSRF prevention)
│   │   ├── context.py             # [Phase 1] Request-scoped & job-scoped ephemeral key lifecycles
│   │   ├── config.py              # [Phase 1] OwnerConfig (from .env) vs. VisitorKeys (ephemeral)
│   │   ├── errors.py              # [Phase 1] Error taxonomy (fail-fast visitor key policies)
│   │   └── tracing.py             # [Phase 7] Privacy-safe distributed tracing engine (metadata-only for visitors)
│   │
│   ├── ingest/
│   │   ├── parsers/               # [Phase 2] Document Parser & Normalization Layer
│   │   │   ├── structured_doc.py  # [Phase 2] Block & StructuredDoc universal schemas
│   │   │   ├── cleanup.py         # [Phase 2] Hyphenation repair & running header/footer stripper
│   │   │   ├── local_pymupdf.py   # [Phase 2] Free local PyMuPDF parser & fast page counter
│   │   │   ├── llamaparse.py      # [Phase 2] LlamaParse cloud adapter & Markdown normalizer
│   │   │   ├── landingai.py       # [Phase 2] Landing AI ADE adapter with spatial bounding boxes
│   │   │   ├── registry.py        # [Phase 2] ParserRegistry factory
│   │   │   └── quality_gate.py    # [Phase 2] Coverage, heading, empty page & garble audit checks
│   │   │
│   │   └── chunking/              # [Phase 3] Hybrid Chunker Subsystem
│   │       ├── models.py          # [Phase 3] ParentChunk, ChildChunk, ChunkingConfig, ChunkingResult
│   │       ├── tokenizer.py       # [Phase 3] Conservative token estimation & truncation
│   │       ├── heading_stack.py   # [Phase 3] Structure pass & breadcrumb trail generator
│   │       ├── table_splitter.py  # [Phase 3] Markdown table splitter with header preservation
│   │       ├── recursive_splitter.py # [Phase 3] Recursive separator cascade with token overlap
│   │       └── hybrid_chunker.py  # [Phase 3] IChunker implementation with heading fusion
│   │
│   ├── retrieval/                 # [Phase 3 & 4] Vector Embeddings, Qdrant Storage & Neural Rerank
│   │   ├── embed.py               # [Phase 3] CohereEmbedder (IEmbedder) with backoff & owner usage meter
│   │   ├── sparse.py              # [Phase 3] LocalSparseVectorizer (in-process BM25 token hashing, $0)
│   │   ├── store.py               # [Phase 3] QdrantVectorStore with hybrid search & scope isolation
│   │   ├── rerank.py              # [Phase 4] CohereReranker (IReranker) with circuit breaker & hybrid fallback
│   │   ├── search.py              # [Phase 4] HybridSearchPipeline with server scope & not-found gate
│   │   └── expansion.py           # [Phase 4] ContextExpander (parent/window expansion with token budget)
│   │
│   ├── storage/                   # [Phase 3] Relational Metadata Storage
│   │   └── db.py                  # [Phase 3] DatabaseManager (SQLite with zero-key security audit)
│   │
│   ├── generation/                # [Phase 4] Answer Synthesis, Citations & Streaming LLM
│   │   ├── prompt.py              # [Phase 4] Input screening & untrusted context formatting
│   │   ├── llm.py                 # [Phase 4] Groq (Owner default) + OpenAI & Anthropic (BYOK) adapters
│   │   ├── citations.py           # [Phase 4] Citation verification & provenance metadata enrichment
│   │   └── rewrite.py             # [Phase 4] Conditional conversational query rewriter
│   │
│   ├── cli.py                     # [Phase 4] Interactive CLI interface (python -m src.cli ask "...")
│   │
│   └── api/                       # [Phase 5 & 6] FastAPI REST API, Session Security & Jobs
│       ├── main.py                # [Phase 5] FastAPI application factory, CORS, request-ID middleware & error handlers
│       ├── sessions.py            # [Phase 5] Session issuance, tier detection & server-derived scope dependency
│       ├── caps.py                # [Phase 5] Owner spend caps, IP rate limits, kill switch & daily budgets
│       ├── chat.py                # [Phase 5] 7-gate chat endpoint, usage meter & demo chips
│       ├── logging.py             # [Phase 5] Privacy-safe structured logging & key leak scrubber
│       ├── connections.py         # [Phase 1] verify_provider_connection pre-flight testing service
│       ├── upload_validation.py   # [Phase 6] Magic bytes, encryption check, and quota estimation
│       ├── jobs.py                # [Phase 6] Asynchronous ingestion worker & fallback state machine
│       ├── lifecycle.py           # [Phase 6] Data deletion (DELETE /session) & background TTL cleanup
│       └── upload.py              # [Phase 6] REST endpoints for uploads, status, and document listing
│
└── tests/
    ├── conftest.py                # [Phase 0] Pytest fixtures and mock keys
    ├── security/                  # [Phase 1, 6 & 7] 27 security & privacy unit tests
    │   ├── test_secret.py         # [Phase 1] Invisibility cloak & Pydantic v2 serialization tests
    │   ├── test_redaction.py      # [Phase 1] Text, dict, and logging redaction tests
    │   ├── test_egress.py         # [Phase 1] Egress allowlist, loopback, and metadata blocking tests
    │   ├── test_context.py        # [Phase 1] Key lifecycle and RAM disposal tests
    │   ├── test_key_leakage.py    # [Phase 1] End-to-end grep audit verifying zero credential leaks
    │   ├── test_upload_security.py# [Phase 6] Ephemeral parser key non-persistence tests
    │   └── test_tracing.py        # [Phase 7] Full-content demo vs metadata-only visitor trace tests
    │
    ├── ingest/                    # [Phase 2 & 3] 24 ingestion & chunking unit tests
    │   ├── test_structured_doc.py # [Phase 2] Block validation and query helper tests
    │   ├── test_cleanup.py        # [Phase 2] Hyphenation and header/footer stripping tests
    │   ├── test_normalizers.py    # [Phase 2] LlamaParse & Landing AI payload translation tests
    │   ├── test_quality_gate.py   # [Phase 2] Pass/warning heuristic tests
    │   ├── test_local_pymupdf.py  # [Phase 2] Real PDF creation, page counting, and extraction tests
    │   ├── test_registry.py       # [Phase 2] Registry resolution and unknown parser tests
    │   ├── test_chunking.py       # [Phase 3] Heading stack, table split, recursive split & fusion tests
    │   └── test_demo_scripts.py   # [Phase 3] Demo corpus ingestion end-to-end test
    │
    ├── retrieval/                 # [Phase 3 & 4] 10 embedding, vector store & reranking unit tests
    │   ├── test_embed.py          # [Phase 3] Cohere embedder adapter, batching, and usage callback tests
    │   ├── test_sparse.py         # [Phase 3] Local sparse vectorizer and deterministic hashing tests
    │   ├── test_store.py          # [Phase 3] Qdrant dual-vector upsert and cross-session isolation tests
    │   ├── test_rerank.py         # [Phase 4] Cohere reranker ordering, fallback, and usage tracking tests
    │   ├── test_search.py         # [Phase 4] Hybrid search pipeline, scope filter, and not-found gate tests
    │   └── test_expansion.py      # [Phase 4] Parent context expansion and deduplication tests
    │
    ├── storage/                   # [Phase 3] 3 relational storage unit tests
    │   └── test_db.py             # [Phase 3] Zero-secret schema audit, parent fetch, and session usage tests
    │
    ├── generation/                # [Phase 4] 11 prompt, citation, and LLM adapter unit tests
    │   ├── test_prompt.py         # [Phase 4] Question validation, injection blocking, and prompt tests
    │   ├── test_citations.py      # [Phase 4] Citation index extraction and hallucination audit tests
    │   ├── test_llm.py            # [Phase 4] Groq, OpenAI, and Anthropic streaming and error tests
    │   └── test_rewrite.py        # [Phase 4] First-turn bypass and conversational rewriting tests
    │
    ├── api/                       # [Phase 5 & 6] 95 REST API, session, upload & lifecycle tests
    │   ├── test_sessions.py       # [Phase 5] Session creation, TTL, tier detection & server-derived scope tests
    │   ├── test_caps.py           # [Phase 5] Spend caps, per-IP rate limits, daily budgets & kill switch tests
    │   ├── test_demo.py           # [Phase 5] Demo mode (Tier A), read-only isolation & usage meter tests
    │   ├── test_privacy_logging.py# [Phase 5] Privacy-safe logging & credential leak grep tests
    │   ├── test_isolation.py      # [Phase 5] Multi-tenant cross-session data isolation tests
    │   ├── test_upload_validation.py # [Phase 6] Magic bytes, password rejection, and page quota checks
    │   ├── test_upload_routes.py  # [Phase 6] Fast upload route validation and 202 status handling
    │   ├── test_jobs.py           # [Phase 6] Background runner execution and state transition tests
    │   └── test_lifecycle.py      # [Phase 6] Instant session wipe and background TTL cleanup tests
    │
    └── eval/                      # [Phase 7] 5 evaluation, ablation & tier verification tests
        └── test_eval.py           # [Phase 7] Golden set validity, Evaluator, AblationRunner & TierVerifier
```

---

## 🚀 How to Run and Verify

### 1. Setup Virtual Environment
```powershell
# Create environment
python -m venv .venv

# Activate environment (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install project and dev dependencies
pip install -e ".[dev]"
```

### 2. Run All Automated Tests
To execute the complete suite of **175 tests**:
```powershell
.venv\Scripts\pytest -v
```
You will see 175 green passes:
* `tests/security/` (27 tests verifying secret masking, log filters, egress blocking, zero leaks in uploads, and privacy-safe traces - **Phase 1, 6 & 7**)
* `tests/ingest/` (24 tests verifying document parsing, cleanup rules, normalizers, quality gates, hybrid chunking, and demo ingestion - **Phase 2 & 3**)
* `tests/retrieval/` (10 tests verifying Cohere embedding batching, local BM25 sparse vectors, Qdrant scope isolation, Cohere reranking, not-found gate, and parent expansion - **Phase 3 & 4**)
* `tests/storage/` (3 tests verifying zero-key schema security, parent context retrieval, and usage tracking - **Phase 3**)
* `tests/generation/` (11 tests verifying question validation, injection protection, citation audits, LLM streaming adapters, and query rewrite - **Phase 4**)
* `tests/api/` (95 tests verifying sessions, atomic caps, upload validation, background job runner, local fallback, lifecycle deletions, and multi-tenant isolation - **Phase 5 & 6**)
* `tests/eval/` (5 tests verifying golden set benchmark validity, metrics computation, ablation runner, threshold tuning, and tier checks - **Phase 7**)

### 3. Run Benchmark Evaluation & Ablation Suite
To run the automated Phase 7 benchmark across all 50 golden queries and export reports to `eval/results/`:
```powershell
python scripts/run_eval.py
```
This produces:
* `eval/results/summary.md`: Executive markdown summary with Recall@5/10, MRR, Faithfulness, and Latency
* `eval/results/metrics.json`: Full machine-readable aggregate metrics
* `eval/results/ablation.md`: Comparative table contrasting Dense, Sparse, Hybrid, Heading Fusion, and Full Production
* `eval/results/thresholds_and_caps.md`: Empirically calibrated Not-Found cutoffs and session spend caps

### 4. Run Code Quality & Linting
```powershell
.venv\Scripts\ruff check .
.venv\Scripts\ruff format --check .
```
Output: `All checks passed! 113 files already formatted.`

### 5. Launch the Web Application & REST API
```powershell
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```
* **Frontend Web Application (Phase 8 UI):** Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.
  - **Tier A (Try Demo):** Instant chat over the pre-indexed corpus with zero API keys required.
  - **Tier B (Upload PDF):** Drag-and-drop your PDF with Free Local PyMuPDF or BYOK cloud parsers.
  - **Tier C (BYOK LLM):** Bring your own Groq, OpenAI, or Anthropic LLM key for expanded quotas.
  - **Provenance Inspector:** Click citation badges (`[1]`, `[2]`) to inspect full retrieved source passages.
* **Interactive Swagger UI:** Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
* **OpenAPI ReDoc:** Open [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc).

### 6. Production deploy (one public URL)
FastAPI serves the API and the built React app together. Qdrant Cloud holds vectors; SQLite lives on a persistent disk at `/data`. Do not split the UI onto a second host.

```powershell
docker compose up --build
python scripts/ingest_demo.py --require-embeddings
python scripts/smoke_prod.py http://127.0.0.1:8000
```

Render/Fly/Railway: use the `Dockerfile`, set owner secrets in the platform dashboard, attach a disk at `/data`, set `FRONTEND_ORIGIN` to that service's https URL, then follow [DEPLOY.md](DEPLOY.md).

### 7. Interactive CLI Q&A
```powershell
# Ask questions over the demo corpus
python -m src.cli ask "What is Acme Corporation's debt-to-equity ratio?"

# Test constitutional rights lookup
python -m src.cli ask "Which freedoms are explicitly protected under the First Amendment?"

# Test not-found cost guard on unanswerable query (exits with $0 LLM generation cost)
python -m src.cli ask "What were the sales figures for Mars rover titanium wheels?"

# Run with reranking disabled for ablation benchmarking
python -m src.cli ask "What is Acme Corporation's debt-to-equity ratio?" --disable-rerank
```

---

## 📈 Master Roadmap & Phase-by-Phase Progress

- [x] **Phase 0: Foundation, Architecture Decisions & Workspace Setup**
  - [x] `docs/DECISIONS.md` (Locked ADRs: 3-tier model, Cohere pinned models, Qdrant hosting)
  - [x] `.env.example` with owner spend controls, session quotas, and kill switches
  - [x] `.github/workflows/ci.yml` (Automated GitHub Actions CI pipeline)
  - [x] `src/interfaces.py` defining decoupled provider contracts (`IParser`, `IChunker`, `IEmbedder`, `IReranker`, `ILLM`)
- [x] **Phase 1: Key Safety, Credential Isolation & Egress Firewall**
  - [x] `src/security/secret.py` (`Secret` type with Pydantic v2 core schema masking)
  - [x] `src/security/redaction.py` (Log filter & regex credential scrubber)
  - [x] `src/security/egress.py` (Outbound domain allowlist eliminating SSRF)
  - [x] `src/security/context.py` (Request-scoped & job-scoped ephemeral RAM shredder)
  - [x] `src/security/errors.py` (Fail-fast policy for visitor keys)
  - [x] `src/api/connections.py` (Pre-flight probe validation service)
  - [x] 22 security unit & key-leak audit tests
- [x] **Phase 2: Parser Layer, Universal Normalization & Quality Gate**
  - [x] `src/ingest/parsers/structured_doc.py` (Universal `Block` & `StructuredDoc` schemas)
  - [x] `src/ingest/parsers/cleanup.py` (Hyphenation repair & running header/footer stripper)
  - [x] `src/ingest/parsers/local_pymupdf.py` (Free local parser & 5ms page counter)
  - [x] `src/ingest/parsers/llamaparse.py` (LlamaParse cloud adapter & Markdown normalizer)
  - [x] `src/ingest/parsers/landingai.py` (Landing AI ADE adapter with spatial bounding boxes)
  - [x] `src/ingest/parsers/registry.py` (Dynamic parser factory)
  - [x] `src/ingest/parsers/quality_gate.py` (Coverage, heading sanity, empty page & garble checks)
  - [x] 17 ingestion & parser unit tests
- [x] **Phase 3: Chunker, Cohere Embeddings & Indexing**
  - [x] `src/ingest/chunking/hybrid_chunker.py` (Structure pass + Recursive splitter + Parent-Child)
  - [x] `src/ingest/chunking/heading_stack.py` & `tokenizer.py` (Heading breadcrumbs and token estimation)
  - [x] `src/ingest/chunking/table_splitter.py` (Markdown table splitting with header preservation)
  - [x] Heading fusion (`embedding_text` with breadcrumbs vs. clean `display_text`)
  - [x] `src/retrieval/embed.py` (Cohere Embed adapter on owner key with batching and usage tracking)
  - [x] `src/retrieval/sparse.py` (Local BM25 token frequency sparse vector calculation, $0 cost)
  - [x] `src/retrieval/store.py` (Qdrant collection setup with payload indexes on `scope` and `doc_id`)
  - [x] `src/storage/db.py` (SQLite schema with zero-secret audit, parent lookups, and session counters)
  - [x] `scripts/ingest_demo.py` (Offline demo corpus ingestion under `scope = "demo"`)
  - [x] 16 Phase 3 unit tests
- [x] **Phase 4: Retrieval (Cohere Rerank) & Generation, CLI**
  - [x] `src/retrieval/search.py` (Hybrid search with server-enforced scope filter `scope IN [session_id, "demo"]`)
  - [x] `src/retrieval/rerank.py` (Cohere Rerank v3.5 behind `IReranker` with timeout, retries, circuit breaker & hybrid fallback)
  - [x] Not-Found Gate (Refuses unanswerable queries early when rerank score < 0.25, saving $0 on LLM generation)
  - [x] `src/retrieval/expansion.py` (Parent/window context expansion bounded to 3,500 token budget with deduplication)
  - [x] `src/generation/prompt.py` (Question screening & untrusted context delimitation preventing prompt injection)
  - [x] `src/generation/llm.py` (Streaming LLM adapters: Owner default Groq + BYOK OpenAI & Anthropic adapters)
  - [x] `src/generation/citations.py` (Citation audit catching hallucinations and enriching verified sources with page/breadcrumbs)
  - [x] `src/generation/rewrite.py` (Conditional query rewrite for multi-turn follow-ups, 0 cost on turn 1)
  - [x] `src/cli.py` (Interactive CLI tool: answer streaming, source provenance, timings, and ablation flags)
  - [x] 28 Phase 4 unit tests
- [x] **Phase 5: API, Sessions, Demo Mode & Owner Cost Controls**
  - [x] `src/api/sessions.py` (Cryptographic session tokens, TTL, server-derived scope mapping, and tier classification)
  - [x] `src/api/caps.py` (Per-IP sliding-window rate limiting, atomic per-session caps, global daily budgets & kill switch)
  - [x] `src/api/chat.py` (Full 7-gate RAG endpoint: input screening, rate limit, kill switch, caps, rerank, not-found gate & token caps)
  - [x] `src/api/chat.py` (Live `/usage` meter endpoint & `/examples` demo question chips)
  - [x] `src/api/logging.py` (Privacy-safe structured logging: operational metadata only, zero question/document/key leakage)
  - [x] `src/api/main.py` (FastAPI application factory, CORS, request ID middleware & global safe exception handling)
  - [x] 60 new Phase 5 unit tests (143 total passing tests across the repo)
- [x] **Phase 6: Upload Flow, Jobs & Data Lifecycle**
  - [x] `src/api/upload_validation.py` (Pre-flight validation: magic bytes, encryption check, page counts, session quotas & chunk estimation)
  - [x] `src/api/jobs.py` (Asynchronous background job runner with state machine: queued -> parsing -> chunking -> embedding -> indexing -> ready)
  - [x] Ephemeral parser key lifecycle with guaranteed `finally` shredding and zero persistence in SQLite or disk
  - [x] Quality Gate integration with non-blocking warnings and automatic local fallback on cloud parser failure
  - [x] Session-scoped parse cache keyed by `(session_id, content_hash, parser, version)`
  - [x] `src/api/lifecycle.py` (`DELETE /session` hard wipe of Qdrant vectors and SQLite records, single-doc deletion, and background TTL cleaner)
  - [x] `src/api/upload.py` (FastAPI router for `/upload/validate`, `/upload`, `/jobs/{job_id}`, `/session/documents`, `DELETE /session`)
  - [x] 23 new Phase 6 unit & integration tests (166 total passing tests across the repo)
- [x] **Phase 7: Evaluation, Tuning & Tracing**
  - [x] `eval/golden_set.jsonl` (50 curated benchmark questions across direct facts, tables/numbers, synthesis, and unanswerables)
  - [x] `eval/evaluate.py` (Recall@5, Recall@10, MRR, Faithfulness, latency p50/p95, and spend measurement engine)
  - [x] `eval/ablation.py` (5-way architectural ablation study isolating Dense, Sparse, Hybrid, Breadcrumb Fusion, and Reranking)
  - [x] `eval/tune_thresholds.py` (Empirical threshold calibration for Not-Found Gate at 0.25 - 0.35 and session spend recommendations)
  - [x] `eval/tier_checks.py` (Automated harness verifying Tier A, B, and C financial boundaries, zero secret persistence, and BYOK isolation)
  - [x] `src/security/tracing.py` (Privacy-preserving distributed tracing: full content for demo/eval, strictly metadata-only for visitor documents)
  - [x] `eval/results/` (Publication-ready markdown and JSON benchmark reports)
  - [x] 9 new Phase 7 unit tests (175 total passing tests across the repo)
- [x] **Phase 8: Frontend (Modern UI with Live Usage Meter)**
- [x] **Phase 9: Hardening, Abuse & Failure Drills**
  - [x] Cost-abuse tests + `scripts/abuse_chat.py` (session/IP/daily caps, kill switch, no uncapped Cohere/LLM path)
  - [x] Daily upload cap, ingest job timeout/cancel, concurrent job queue cap, body-size reject (CAPTCHA cut)
  - [x] Failure drills: mid-job cancel, parser/LLM/embed/Qdrant outages, rerank hybrid fallback
  - [x] Production CORS/HSTS/CSP, HTTPS-only, HttpOnly session cookie, `/health` readiness, `/metrics` (no content), `/terms`
  - [x] First-upload terms checkbox (UI + API gate)
  - [x] `scripts/health_check.py` uptime probe and `scripts/audit_deps.py` (pip-audit / npm audit)
- [x] **Phase 10: Production Deployment & Smoke Tests**
  - [x] Multi-stage `Dockerfile` + `docker-compose.yml` (API + SPA + Qdrant)
  - [x] SQLite on `DATA_DIR` / persistent volume; production Qdrant refuses in-memory fallback
  - [x] Interrupted in-flight jobs marked failed on boot; `/health` 503 in production if SQLite or Qdrant is down
  - [x] `render.yaml`, [DEPLOY.md](DEPLOY.md) rollback notes, CI image build
  - [x] `scripts/smoke_prod.py` for Tiers A / B / C against one public origin
- [ ] *Up Next:* **Phase 11: Demo Video, Results & Launch**

