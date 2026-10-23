# Provenance RAG

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0+-green.svg)](https://fastapi.tiangolo.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-2.9.0+-blue.svg)](https://docs.pydantic.dev/)
[![Pytest](https://img.shields.io/badge/pytest-39%20passed-brightgreen.svg)](https://docs.pytest.org/)
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
7. [🔍 Real-World Walkthrough: Trace of an Uploaded Document](#-real-world-walkthrough-trace-of-an-uploaded-document)
8. [🗺️ Codebase Directory Map (Organized by Phase)](#️-codebase-directory-map-organized-by-phase)
9. [🚀 How to Run and Verify](#-how-to-run-and-verify)
10. [📈 Master Roadmap & Phase-by-Phase Progress](#-master-roadmap--phase-by-phase-progress)

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
  print(key)          # Prints: ***
  print(repr(key))    # Prints: Secret('***')
  dict_payload = {"key": key}
  json.dumps(...)     # Serializes as: {"key": "***"}
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
    type: BlockType       # HEADING, PARAGRAPH, LIST_ITEM, TABLE, CODE, FIGURE, CAPTION
    text: str             # Cleaned text (tables formatted as Markdown)
    level: int | None     # 1..6 if heading, otherwise None
    page: int             # 1-indexed page number
    bbox: list[float]     # [top, left, bottom, right] coordinates (for citation highlighting)
    order: int            # Sequential reading order

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
* *The document is ready for Phase 3 chunking!*

---

## 🗺️ Codebase Directory Map (Organized by Phase)

```text
provenance-rag/
├── README.md                      # Comprehensive system guide & documentation
├── pyproject.toml                 # [Phase 0] Dependencies, build tooling, ruff, & pytest config
├── .gitignore                     # [Phase 0] Protection for .env, virtualenvs, uploads, & caches
├── .env.example                   # [Phase 0] Owner configuration template & spend controls
├── docs/
│   └── DECISIONS.md               # [Phase 0] Architecture Decision Records (ADRs)
├── demo_corpus/                   # [Phase 0] Public documents for Tier A (zero-key demo)
├── samples/                       # [Phase 0] Sample PDFs for testing and quality gate benchmarks
│
├── src/
│   ├── interfaces.py              # [Phase 0] Blueprints: IParser, IChunker, IEmbedder, IReranker, ILLM
│   │
│   ├── security/                  # [Phase 1] The Security Moat
│   │   ├── secret.py              # [Phase 1] Secret wrapper class (str/repr/json -> '***')
│   │   ├── redaction.py           # [Phase 1] Regex logging filter & dictionary credential scrubber
│   │   ├── egress.py              # [Phase 1] Outbound domain allowlist (SSRF prevention)
│   │   ├── context.py             # [Phase 1] Request-scoped & job-scoped ephemeral key lifecycles
│   │   ├── config.py              # [Phase 1] OwnerConfig (from .env) vs. VisitorKeys (ephemeral)
│   │   └── errors.py              # [Phase 1] Error taxonomy (fail-fast visitor key policies)
│   │
│   ├── ingest/
│   │   └── parsers/               # [Phase 2] Document Parser & Normalization Layer
│   │       ├── structured_doc.py  # [Phase 2] Block & StructuredDoc universal schemas
│   │       ├── cleanup.py         # [Phase 2] Hyphenation repair & running header/footer stripper
│   │       ├── local_pymupdf.py   # [Phase 2] Free local PyMuPDF parser & fast page counter
│   │       ├── llamaparse.py      # [Phase 2] LlamaParse cloud adapter & Markdown normalizer
│   │       ├── landingai.py       # [Phase 2] Landing AI ADE adapter with spatial bounding boxes
│   │       ├── registry.py        # [Phase 2] ParserRegistry factory
│   │       └── quality_gate.py    # [Phase 2] Coverage, heading, empty page & garble audit checks
│   │
│   └── api/
│       └── connections.py         # [Phase 1] verify_provider_connection pre-flight testing service
│
└── tests/
    ├── conftest.py                # [Phase 0] Pytest fixtures and mock keys
    ├── security/                  # [Phase 1] 22 security unit tests
    │   ├── test_secret.py         # [Phase 1] Invisibility cloak & Pydantic v2 serialization tests
    │   ├── test_redaction.py      # [Phase 1] Text, dict, and logging redaction tests
    │   ├── test_egress.py         # [Phase 1] Egress allowlist, loopback, and metadata blocking tests
    │   ├── test_context.py        # [Phase 1] Key lifecycle and RAM disposal tests
    │   └── test_key_leakage.py    # [Phase 1] End-to-end grep audit verifying zero credential leaks
    │
    └── ingest/                    # [Phase 2] 17 document ingestion unit tests
        ├── test_structured_doc.py # [Phase 2] Block validation and query helper tests
        ├── test_cleanup.py        # [Phase 2] Hyphenation and header/footer stripping tests
        ├── test_normalizers.py    # [Phase 2] LlamaParse & Landing AI payload translation tests
        ├── test_quality_gate.py   # [Phase 2] Pass/warning heuristic tests
        ├── test_local_pymupdf.py  # [Phase 2] Real PDF creation, page counting, and extraction tests
        └── test_registry.py       # [Phase 2] Registry resolution and unknown parser tests
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
To execute the complete suite of **39 tests**:
```powershell
.venv\Scripts\pytest -v
```
You will see 39 green passes:
* `tests/security/` (22 tests verifying secret masking, log filters, egress blocking, and zero leaks - **Phase 1**)
* `tests/ingest/` (17 tests verifying document parsing, cleanup rules, normalizers, and quality gates - **Phase 2**)

### 3. Run Code Quality & Linting
```powershell
.venv\Scripts\ruff check .
```
Output: `All checks passed!`

---

## 📈 Master Roadmap & Phase-by-Phase Progress

- [x] **Phase 0: Foundation, Architecture Decisions & Workspace Setup**
  - [x] `docs/DECISIONS.md` (Locked ADRs: 3-tier model, Cohere pinned models, Qdrant hosting)
  - [x] `.env.example` with owner spend controls, session quotas, and kill switches
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
- [ ] *Up Next:* **Phase 3: Chunker, Cohere Embeddings & Indexing**
  - [ ] Hybrid Chunker (Structure-aware heading stack + Recursive splitter + Parent-Child)
  - [ ] Heading fusion (`embedding_text` with breadcrumbs vs. clean `display_text`)
  - [ ] Cohere Embed adapter (document vs. query input types on owner key)
  - [ ] Local FastEmbed/BM25 sparse vector computation
  - [ ] Qdrant Cloud collection setup with payload indexes on `scope`
  - [ ] Offline demo corpus ingestion under `scope = "demo"`
- [ ] *Up Next:* **Phase 4: Retrieval (Cohere Rerank) & Generation, CLI**
- [ ] *Up Next:* **Phase 5: API, Sessions, Demo Mode & Owner Cost Controls**
- [ ] *Up Next:* **Phase 6: Upload Flow, Jobs & Data Lifecycle**
- [ ] *Up Next:* **Phase 7: Evaluation, Tuning & Tracing**
- [ ] *Up Next:* **Phase 8: Frontend (Modern UI with Live Usage Meter)**
- [ ] *Up Next:* **Phase 9: Hardening, Abuse & Failure Drills**
- [ ] *Up Next:* **Phase 10: Production Deployment & Smoke Tests**
- [ ] *Up Next:* **Phase 11: Demo Video, Results & Launch**
