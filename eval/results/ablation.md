# Provenance RAG: Retrieval Strategy Ablation

Empirical comparison of four retrieval techniques on the 50-query golden set. Simple and semantic configs use separate chunk indexes; hybrid and rerank reuse the semantic index.

## Ablation Comparison Table

| # | Configuration | Recall@5 | Recall@10 | MRR | Faithfulness | Not-Found Acc | Latency (p95) |
|---|---|---|---|---|---|---|---|
| 1 | **Simple Chunking (Fixed-size Segments, Dense Vector Search, No Rerank)** | `60.0%` | `65.71%` | `0.378` | `16.33%` | `0.0%` | `1.0ms` |
| 2 | **Semantic Chunking (Structure & Heading Aware, Dense Vector Search, No Rerank)** | `88.57%` | `91.43%` | `0.731` | `53.0%` | `0.0%` | `1.0ms` |
| 3 | **Hybrid Search (Semantic Chunks + Dense Vector + BM25 Sparse, No Rerank)** | `91.43%` | `100.0%` | `0.753` | `55.0%` | `0.0%` | `1.4ms` |
| 4 | **Reranking (Semantic Chunks + Hybrid Search + Lexical/Cohere Rerank + Parent Expansion)** | `100.0%` | `100.0%` | `0.971` | `88.67%` | `100.0%` | `4.4ms` |

## Senior Takeaways

1. **Best measured configuration:** `4_reranking` (MRR `0.971`, Recall@5 `100.0%`).

2. **Weakest measured configuration:** `1_simple_chunking` (MRR `0.378`, Recall@5 `60.0%`).

3. **Semantic vs simple chunking:** Recall@5 delta is `28.57` points because heading-aware windows keep fiscal-year labels with the figures.

4. **Rerank vs hybrid:** MRR moves from `0.753` to `0.971`; not-found accuracy moves from `0.0%` to `100.0%` because the second-stage scorer down-ranks out-of-corpus terms.
