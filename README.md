# Provenance RAG

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0+-green.svg)](https://fastapi.tiangolo.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-2.9.0+-blue.svg)](https://docs.pydantic.dev/)
[![Pytest](https://img.shields.io/badge/pytest-39%20passed-brightgreen.svg)](https://docs.pytest.org/)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

> A production-grade, financial-isolated, multi-provider Retrieval-Augmented Generation (RAG) framework with ephemeral visitor key handling, egress domain firewalling, universal document normalization, and parse quality gating.

---

## 🏗️ Architecture & Access Tiers

Provenance RAG enforces strict financial and security isolation between owner-funded services and visitor-provided capabilities:

```
                      ┌──────────────────────────────────────────────┐
                      │              Access Tiers                    │
                      ├──────────────────────────────────────────────┤
                      │ Tier A: Zero-key Demo (Owner pays, capped)   │
                      │ Tier B: Upload PDF (Visitor parser / PyMuPDF)│
                      │ Tier C: Full BYOK (Visitor parser + LLM)     │
                      └──────────────────────────────────────────────┘
                                              │
                  ┌───────────────────────────┴───────────────────────────┐
                  ▼                                                       ▼
      [ Ingestion Pipeline ]                                      [ Retrieval & Chat ]
   Upload PDF -> Validate & Count                              User Question -> Session / Caps
   -> Selected Parser (Memory key)                             -> Rewrite (if follow-up)
   -> Normalize (StructuredDoc)                                -> Cohere Embed (Query)
   -> Quality Gate (Coverage check)                            -> Hybrid Search (Scope filter)
   -> Hybrid Chunker + Heading Fusion                          -> Cohere Rerank (Top 5)
   -> Cohere Embed + Local Sparse                              -> Not-Found Gate (< Threshold)
   -> Qdrant (Scope) + SQL (Parents)                           -> Context Budget / Expansion
                                                               -> LLM (Owner or Visitor Key)
                                                               -> Citation Check & Stream
```

### The Three Access Tiers

| Tier | What Visitor Provides | What You Can Do | Who Pays What |
|---|---|---|---|
| **Tier A (Demo)** | Nothing (zero keys) | Chat over pre-indexed public corpus (`scope = "demo"`) | **Owner**: Cohere Embed, Cohere Rerank, Default LLM (strict daily/session caps) |
| **Tier B (Upload)** | PDF + Free Local Parser **or** Visitor Parser Key | Parse and chat with own documents | **Visitor**: Parsing (own key or free local). **Owner**: Cohere Embed, Rerank, Default LLM within caps |
| **Tier C (Full BYOK)** | PDF + Parser Key + **Own LLM Key** | Full custom model generation and higher question caps | **Visitor**: Parsing + Answers. **Owner**: Cohere Embed & Rerank within caps |

---

## 🧩 Complete Implementation Blueprint

### 1. Foundation & Decisions
* **Decision Records (`docs/DECISIONS.md`):** Locked architecture defining the 3-tier boundary, scoping BYOK strictly to PDF parsers and LLMs, pinning Cohere as single embedding/reranking provider, and enforcing owner-hosted Qdrant with scope-based TTL isolation.
* **Owner Protection & Caps (`.env.example` & `src/security/config.py`):**
  * Per-session limits: `1,500` embedded chunks, `30` rerank calls, `15` owner-LLM questions, `100` BYOK questions.
  * Daily limits: `25,000` embedded chunks, `500` rerank calls, `500,000` owner LLM tokens.
  * Emergency kill switches to disable file uploads or owner-funded LLM responses without code redeployment.

---

### 2. Key Safety & Provider Layer (`src/security/`)
A leak-proof credential management layer ensuring visitor keys are never stored on disk, logged, or exfiltrated:

* **The Invisibility Cloak (`src/security/secret.py`):**
  * Wraps API keys in a `Secret` class where `str()`, `repr()`, and Pydantic v2 JSON serialization always output `"***"`.
  * The raw key is inaccessible unless code explicitly invokes `.reveal()` right before dispatching an HTTP request.
* **Defense-in-Depth Redaction (`src/security/redaction.py`):**
  * Intercepts standard Python logging, error messages, and dictionaries.
  * Auto-redacts `Bearer <token>`, `sk-...` (OpenAI), `co-...` (Cohere), `gsk_...` (Groq), `anthropic-...` (Anthropic), and `llx-...` (LlamaParse) patterns.
* **Outbound Egress Firewall (`src/security/egress.py`):**
  * Eliminates Server-Side Request Forgery (SSRF) and data theft.
  * Custom HTTPX transport checks destination hosts against a hardcoded domain allowlist:
    * `api.cohere.com`, `api.cohere.ai`
    * `api.cloud.llamaindex.ai`
    * `api.landing.ai`, `api.va.landing.ai`
    * `api.unstructured.io`
    * `api.groq.com`, `api.openai.com`, `api.anthropic.com`
  * Outright blocks private IPs (RFC 1918), loopback, cloud metadata endpoints (`169.254.169.254`), and open redirects.
* **Ephemeral Lifecycle Shredder (`src/security/context.py`):**
  * **Visitor LLM Keys:** Tied to Python `contextvars` for a single turn; discarded upon response completion.
  * **Visitor Parser Keys:** Passed to `EphemeralJobContext` in memory during ingestion only; wiped in a `finally` block.
* **Fail-Fast Error Taxonomy (`src/security/errors.py`):**
  * Categorizes errors into `InvalidKeyError`, `QuotaExhaustedError`, `RateLimitedError`, and `EgressBlockedError`.
  * Visitor key errors are marked `retryable = False` to prevent retry storms and UI freezing.
* **Pre-flight Key Verification (`src/api/connections.py`):**
  * `verify_provider_connection()` sends lightweight, non-credit-consuming probe calls to confirm a visitor key is valid before any PDF parsing begins.

---

### 3. Document Ingestion, Parser Layer & Quality Gate (`src/ingest/parsers/`)

```
                       [ VISITOR UPLOADS A PDF ]
                                   │
                                   ▼
        ┌────────────────────────────────────────────────────────┐
        │  PARSER SELECTION (Visitor picks one)                 │
        │  • Free Local Parser (PyMuPDF - zero cost, no key)     │
        │  • LlamaParse (Visitor key)                           │
        │  • Landing AI ADE (Visitor key)                       │
        └──────────────────────────┬─────────────────────────────┘
                                   │
                                   ▼
        ┌────────────────────────────────────────────────────────┐
        │  CLEANUP & NORMALIZATION                               │
        │  • Fix hyphenated line breaks ("bil-\nlion")           │
        │  • Strip repetitive headers & footers across pages     │
        │  • Map to universal StructuredDoc & Block schema       │
        └──────────────────────────┬─────────────────────────────┘
                                   │
                                   ▼
        ┌────────────────────────────────────────────────────────┐
        │  QUALITY GATE INSPECTION                               │
        │  • Text coverage vs. PyMuPDF raw baseline (>= 65%)     │
        │  • Heading sanity & hierarchy check                    │
        │  • Empty page & garbled text detection                 │
        └──────────────────────────┬─────────────────────────────┘
                                   │
                                   ▼
               (Ready for Chunking & Cohere Embedding)
```

#### A. Universal Schema (`src/ingest/parsers/structured_doc.py`)
Decouples downstream chunkers and vector databases from individual parser SDKs:
* **`Block`:** Semantic unit carrying `type` (`heading`, `paragraph`, `list_item`, `table`, `code`, `figure`, `caption`), `level` (`1..6` for headings), `page`, and spatial `bbox` coordinates (`[top, left, bottom, right]`).
* **`StructuredDoc`:** Standard document container holding metadata (`doc_id`, `title`, `page_count`, `parser_used`) and ordered blocks.

#### B. The Cleaning Engine (`src/ingest/parsers/cleanup.py`)
* **Hyphenation Fixer:** Reconstructs words broken by line wrapping (`"multi-\nprocess"` $\to$ `"multiprocess"`).
* **Header & Footer Stripper:** Detects identical text repeated across $\ge 40\%$ of pages (e.g., `"Company Confidential"`, `"Page 2 of 10"`) and strips them so duplicate noise does not corrupt retrieval embeddings.
* **Whitespace & Unicode Normalizer:** Standardizes spaces, strips zero-width/control characters, and re-indexes block order sequentially.

#### C. Local PyMuPDF Parser (`src/ingest/parsers/local_pymupdf.py`)
* **Fast Local Page Counting (`count_pages`):** Counts pages in 5ms locally for $0.00, protecting users from accidentally uploading a 500-page file that would deplete their cloud credits.
* **Local Parsing Engine:** Calibrates document font statistics to infer heading levels (H1, H2, H3) based on relative font size and boldness.
* **Ground Truth Extraction (`extract_raw_reference_text`):** Provides a raw text baseline for the Quality Gate.

#### D. LlamaParse Adapter & Normalizer (`src/ingest/parsers/llamaparse.py`)
* Connects to LlamaIndex Cloud through the secure egress transport using the visitor's `Secret` key.
* Translates Markdown headings (`#`), pipe tables (`|...|`), lists, and code fences into `StructuredDoc` blocks while maintaining page tracking.

#### E. Landing AI ADE Adapter & Normalizer (`src/ingest/parsers/landingai.py`)
* Connects to Landing AI Agentic Document Extraction (`api.va.landing.ai`).
* Simultaneously extracts clean Markdown content and exact **grounding bounding boxes** (`chunk.grounding.box`), populating `Block.bbox` for visual citation highlighting.

#### F. Dynamic Parser Registry (`src/ingest/parsers/registry.py`)
* Provides a factory to look up and register parsers dynamically (`default_parser_registry.get("local_pymupdf")`, `"llamaparse"`, `"landingai"`).

#### G. The Quality Gate (`src/ingest/parsers/quality_gate.py`)
Prevents corrupted or silently dropped parser outputs from entering the vector index:
1. **Text Coverage Check:** Compares parsed length against the PyMuPDF raw baseline; warns if coverage is $< 65\%$.
2. **Heading Sanity Check:** Warns if a multi-page document has 0 headings or erratic hierarchy jumps (e.g. H1 $\to$ H5).
3. **Empty Page Check:** Detects if any page produced zero extracted blocks.
4. **Garbled Text Check:** Flags high density of unicode replacement characters (`\ufffd`).

---

## 🧪 Concrete End-to-End Walkthrough

Here is what happens when a 3-page document (`Apple_Q3_Report.pdf`) is processed:

```
[ INPUT PDF ]
Page 1: "Apple Inc. Confidential" (top), "Financial Results Q3" (24pt), "Executive Summary" (16pt), "Revenue: $85.8 bil-\nlion", "Page 1 of 3" (bottom)
Page 2: "Apple Inc. Confidential" (top), "Segment Performance" (16pt), Table: | Category | Revenue |, "Page 2 of 3" (bottom)
Page 3: "Apple Inc. Confidential" (top), "Conclusion" (16pt), "Strong momentum globally.", "Page 3 of 3" (bottom)

1. Local Page Count (local_pymupdf.py):
   -> Detected 3 pages locally in 5ms ($0.00 cost). Verified within session cap of 30 pages.

2. Document Parsing (PyMuPDF / LlamaParse / Landing AI):
   -> Extracted raw text, headings, tables, and paragraphs.

3. Document Cleanup (cleanup.py):
   -> "bil-\nlion" normalized to "billion".
   -> "Apple Inc. Confidential" detected on pages 1, 2, and 3: STRIPPED as running header.
   -> "Page X of 3" STRIPPED as running footer.

4. Structured Output (structured_doc.py):
   Block 0: [HEADING Level 1] "Financial Results Q3" (Page 1)
   Block 1: [HEADING Level 2] "Executive Summary" (Page 1)
   Block 2: [PARAGRAPH]       "Revenue: $85.8 billion" (Page 1)
   Block 3: [HEADING Level 2] "Segment Performance" (Page 2)
   Block 4: [TABLE]           "| Category | Revenue |\n| iPhone | $39.3B |" (Page 2)
   Block 5: [HEADING Level 2] "Conclusion" (Page 3)
   Block 6: [PARAGRAPH]       "Strong momentum globally." (Page 3)

5. Quality Gate Inspection (quality_gate.py):
   -> Text Coverage: 98.4% (PASS)
   -> Heading Structure: 4 headings across 3 pages, no erratic jumps (PASS)
   -> Missing Pages: None (PASS)
   -> Garbled Characters: 0.00% (PASS)
   Result: passed=True, has_warnings=False. Ready for Phase 3!
```

---

## 🛠️ Development & Testing

### Running Tests
The test suite contains **39 automated tests** covering key safety, redaction filters, egress blocking, parser adapters, cleanup rules, and quality gates:

```powershell
# Run the complete test suite
.venv\Scripts\pytest -v

# Run only security & key leakage tests
.venv\Scripts\pytest tests/security/

# Run only ingestion & parser tests
.venv\Scripts\pytest tests/ingest/
```

### Running Linting & Quality Checks
```powershell
.venv\Scripts\ruff check .
```

---

## 🗺️ Roadmap & Current Status

- [x] **Repository Foundation & Architecture Decisions**
- [x] **Secret Protection (`Secret`), Redaction Filter, & Egress Firewall**
- [x] **Ephemeral Memory-Only Key Transport (`contextvars` & Job Contexts)**
- [x] **Spend Controls, Access Tiers, & Preflight Key Verification**
- [x] **Universal `StructuredDoc` & `Block` Data Contracts**
- [x] **Free Local Parser (`LocalPyMuPDFParser`) & Fast Page Counter**
- [x] **LlamaParse Adapter & Markdown Normalizer**
- [x] **Landing AI ADE Adapter with Spatial Bounding Box Grounding**
- [x] **Document Cleanup Engine (Hyphenation & Header/Footer Stripping)**
- [x] **Parse Quality Gate (Coverage, Heading, and Garble Audits)**
- [ ] *Next:* Hybrid Chunker (Recursive + Parent-Child with Heading Fusion)
- [ ] *Next:* Cohere Embed Adapter & Dense/Sparse Vector Ingestion into Qdrant
- [ ] *Next:* Retrieval Pipeline (Hybrid Search + Cohere Rerank + Not-Found Gate)
- [ ] *Next:* Citation-Backed Generation & Privacy-Safe Tracing
- [ ] *Next:* Modern UI & Public Deployment
