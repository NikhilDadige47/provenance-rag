# Launch

Drafts only. Do not post these until the demo video is at the top of the README and the live URL is filled in.

## Short post

Most public RAG demos either ask for five API keys or put the host’s key where a loop can drain it.

Provenance RAG lets you ask a pre-stored filing with no key. The answer cites the page, or it refuses when the pages do not support an answer. Uploads stay in a two-hour session. Embeddings and rerank stay on one capped owner key. A model key is optional and is not stored.

On a 50-question offline golden set, hybrid search plus rerank reached Recall@5 of 100% and MRR of 0.971. The not-found check caught every trick question. Those numbers are from the local harness, not a live Cohere bill.

Link: (live URL)

## Two-minute walkthrough

1. **Why three tiers.** Reviewers will not paste keys. The demo has to work with none. Upload is the next step. A personal model key is only for people who want more answers than the owner cap allows.
2. **How keys are protected.** Owner keys live in the host environment. A visitor key is memory for one job or one question. Tests grep logs, SQL, and responses for leaked keys. The honest limit: the key still transits the server, so use a revocable key with a spend cap.
3. **How spend is capped.** Caps run before Cohere and before the LLM. Fifteen owner-funded answers a day on a connection. The not-found gate skips the model when retrieval is weak. A kill switch and an “at capacity” state stop the demo when the owner budget is gone.
4. **How it was evaluated.** Fifty questions over the demo filings, including questions that are not in the documents. The table in the README compares fixed chunks, heading-aware chunks, hybrid search, and rerank. Faithfulness in that table is keyword overlap. Recall@5 is a page hit on the labeled document.
