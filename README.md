# <img src="frontend-react/src/assets/logo.png" width="48" alt=""> Provenance RAG

Ask a document a question. The answer points to the page it came from. If the document does not say it, the system refuses and does not call the model.

The pre-stored filings need no account. An upload stays in its own session and is deleted after two hours. Embeddings and reranking stay on one capped Cohere key. A parser key or a model key is optional, used for that step, and never written down.

| | |
|---|---|
| **Try it** | Pre-stored filings, no key |
| **Proof** | 50 questions. Recall@5 **100%**, MRR **0.971**, not-found accuracy **100%** |
| **Spend** | Caps run before any paid call. A weak retrieval never reaches the LLM |
| **Keys** | Visitor keys stay in memory, then they are gone |

No public URL is stored in this repo. Deploy with [DEPLOY.md](DEPLOY.md). The demo script is [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Architecture

![Provenance RAG high-level architecture](design-system/provenance-rag/image.png)

The browser talks only to FastAPI. Ingest parses, chunks, and embeds. Retrieval searches, reranks, and answers. Children live in Qdrant. Parents and session rows live in SQL. A two-hour TTL wipe removes both. Cohere is the owner embedder and reranker. Groq is the default model. OpenAI and Anthropic are used only when the visitor pastes a key. LlamaParse and Landing AI are optional parsers. PyMuPDF needs no key.

## Decisions

| Question | Decision |
|---|---|
| Who pays for embeddings and reranking? | The owner, on one Cohere key, with per-session and daily caps |
| Who pays for the answer? | The owner by default, tightly capped. The visitor, if they paste an LLM key |
| Who pays for parsing? | The visitor, if they paste a parser key. Nobody, if they use local PyMuPDF |
| Where do vectors live? | The owner's Qdrant. Every chunk has a `scope`. Search cannot cross sessions |
| Can a visitor point the app at their own URL? | No. Adapters call a fixed host list, so there is no SSRF path |

Why the rest of the shape is what it is:

- **Three tiers.** A reviewer can try the demo with nothing to paste. Upload and a personal model key are optional.
- **BYOK stops at the parser and the LLM.** A visitor embedder would break the shared index and the shared score scale.
- **Quality gate before embed.** A bad parse is flagged before anyone pays to store it.
- **Parent-child chunks.** Search ranks a small heading-aware child. The model reads the parent, so a figure stays next to its heading. `embedding_text` carries the breadcrumb. `display_text` stays clean.
- **Hybrid search, then rerank.** Dense Cohere vectors plus a local BM25 vector. Rerank runs on the short list. A score under the cutoff never calls the model.

## Three ways in

| Path | You bring | You get | Who pays |
|---|---|---|---|
| **Demo** | Nothing | Questions over the pre-stored filings | Owner: Cohere embed, Cohere rerank, Groq. **15** free answers a day on this connection |
| **Upload** | A PDF | Up to **3** PDFs and **30** pages. Your file never joins the demo set | Owner pays embed, rerank, and answers, inside the same caps. Local parse is free |
| **Your model** | An optional Groq, OpenAI, or Anthropic key | The same upload flow, up to **100** answers this session | You pay your provider. The owner still pays embed and rerank |

## Evaluation

50 questions over the demo filings: direct facts, table figures, questions that need more than one section, and questions that are not in the documents. Offline harness, 30 October 2026. Local hashing embeddings and a lexical reranker. **Zero Cohere calls.** Reproduce it with `python scripts/run_eval.py`.

| Metric | Measures | Result | Bar |
|---|---|---:|---|
| Recall@5 | Right page in the top 5 | **100%** | ≥ 85% |
| Recall@10 | Right page in the top 10 | **100%** | ≥ 90% |
| MRR | How high the right page ranked | **0.971** | ≥ 0.70 |
| Faithfulness | Labeled keywords present in the answer | **88.7%** | ≥ 90% |
| Not-found accuracy | Trick questions refused | **100%** | 100% |
| Citation accuracy | Cited ids were in the retrieved passages | **100%** | ≥ 95% |
| Latency p50 / p95 | End to end on this run | **342 ms / 463 ms** | — |
| Cost per query | Estimated from tokens on this run | **$0.00003** | — |

Faithfulness here is keyword overlap with the labeled answer. It is not an LLM judge. 88.7% missed the 90% bar. Answerable questions scored at least 0.70. Trick questions scored at most 0.15. The tuned cutoff is 0.35. About 50 tokens per answer. Full write-up: [eval/results/summary.md](eval/results/summary.md), [eval/results/ablation.md](eval/results/ablation.md), [eval/results/thresholds_and_caps.md](eval/results/thresholds_and_caps.md).

### Ablation

Same 50 questions. Each row adds the next retrieval choice. Heading fusion is inside the heading-aware row. Parent-window expansion is inside the last row. A parser bake-off was not run.

| Configuration | Recall@5 | Recall@10 | MRR | Faithfulness | Not-found | p95 |
|---|---:|---:|---:|---:|---:|---:|
| Fixed-size chunks, dense only | 60.0% | 65.7% | 0.378 | 16.3% | 0% | 1 ms |
| Heading-aware chunks, dense only | 88.6% | 91.4% | 0.731 | 53.0% | 0% | 2 ms |
| Hybrid dense + sparse | 91.4% | 100% | 0.753 | 55.0% | 0% | 2 ms |
| **Hybrid + rerank + parent window** | **100%** | **100%** | **0.971** | **88.7%** | **100%** | **448 ms** |

Heading-aware chunks move Recall@5 from 60% to 89%. Rerank moves MRR from 0.75 to 0.97 and is what makes every trick question refuse.

Try these from `eval/golden_set.jsonl`:

- “What was Apple's total net sales in fiscal year 2024?” → $391,035 million, 2024 annual report, page 35.
- “What was Apple's total copper mining revenue on Mars in FY2024?” → refuse, and do not call the model.

## Keys and privacy

Paste a key on the upload screen. It lives in memory for that job or that question, then it is dropped. It is not written to SQLite, logs, traces, or disk.

| Key | Get one | Grant this |
|---|---|---|
| Local PDF parse | Nothing. PyMuPDF runs here. | No key |
| LlamaParse | [LlamaCloud](https://cloud.llamaindex.ai/) | A key with a small credit limit |
| Landing AI | [Landing AI](https://landing.ai/) | A key with a small credit limit |
| Groq, OpenAI, Anthropic | That provider’s API settings | One chat model, a monthly spend cap, and the right to revoke it |

| Data | Goes to | Kept? |
|---|---|---|
| Owner Cohere, Groq, Qdrant, Turso keys | The host environment | Secret store only. Not in git |
| Visitor parser or LLM key | That provider, from memory | No |
| Uploaded PDF | The parser you picked, then Cohere, then the active LLM | Session vectors and rows. Deleted at two hours, on delete, or when the session ends |
| Demo filings | Read-only scope `demo` | Shared. Uploads are never copied in |

Delete in the app removes that session’s vectors, SQL rows, and cached parses. It leaves the demo corpus in place. Terms: [TERMS.md](TERMS.md).

## Limits

- A pasted key crosses this server in memory. Leak tests cover logs and storage. You still have to trust the host. Use a key you can revoke.
- Owner caps are enforced. At the limit the demo says it is at capacity, including when the Cohere or Groq budget is spent.
- A new embed model or a new `EMBEDDING_VERSION` means re-indexing. Old vectors are refused until `scripts/reembed_demo.py` has run.
- The tables above are the offline harness. Live Cohere latency and dollars will differ.

## What this demo leaves for production

| This demo | A hosted product |
|---|---|
| In-process job runner | Durable queue, retries, dead-letter, short-lived tokens for keys |
| Session id, no accounts | Auth, tenants, an access check on every chunk |
| Session caps | Plans, per-tenant quotas, billing |
| One owner Cohere key | Per-tenant keys, or a gateway with a budget |
| Key pasted per request | A vault, or an organization gateway |
| Re-upload to change parser | Versioned collections and a blue/green swap |
| Warn on a bad parse | Parser routing with its own budget |
| Basic tracing | SLOs and per-tenant cost |

## Run it

Offline checks need no API keys.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts/run_eval.py
pytest
```

To open the app, copy `.env.example` to `.env` and set the owner keys (Cohere, Groq, Qdrant). Do not commit `.env`.

```powershell
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
cd frontend-react
npm install
npm run dev
```

Load the demo index once with `python scripts/ingest_demo.py --require-embeddings`. A single-process serve is `npm run build` in `frontend-react`, then [http://127.0.0.1:8000/](http://127.0.0.1:8000/). `--live` on the eval script searches the real Qdrant index and spends Cohere credits.

```
src/api          sessions, upload, chat, caps
src/ingest       parsers, quality gate, chunking
src/retrieval    Cohere embed, local BM25, Qdrant, rerank
src/generation   prompt, Groq / OpenAI / Anthropic, citations
src/security     secrets, egress allowlist, redaction, spend caps
eval             50-question golden set and ablation
frontend-react   landing page, demo, upload, chat
```

Python 3.11, FastAPI, Qdrant, Cohere, Groq, React. The phase-by-phase build log is [docs/BUILD_LOG.md](docs/BUILD_LOG.md). Deploy notes are in [DEPLOY.md](DEPLOY.md). Release notes are in [CHANGELOG.md](CHANGELOG.md).
