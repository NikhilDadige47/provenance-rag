# Changelog

## 1.0.0

Public demo of Provenance RAG.

- Demo over the pre-stored filings, with no visitor key.
- PDF upload in an isolated session, local parse by default, optional cloud parser key.
- Optional Groq, OpenAI, or Anthropic key for answers. The key is not stored.
- Hybrid retrieval, Cohere rerank, a not-found cutoff, and citation checks.
- Owner caps on questions, uploads, and provider spend.
- Offline 50-question golden set and ablation table in `eval/results/`.

The git tag `v1.0.0` is not created yet. Create it from a clean commit when the demo video and live URL are in the README.
