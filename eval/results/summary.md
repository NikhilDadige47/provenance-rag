# Provenance RAG: Phase 7 Benchmark Evaluation Report

**Date:** 2026-10-28 15:30:36 UTC  
**Total Benchmark Queries:** 50  

## 🎯 Retrieval & Ranking Performance

| Metric | Value | Target Goal | Status |
|---|---|---|---|
| **Recall@5** | `100.0%` | >= 85% | PASS |
| **Recall@10** | `100.0%` | >= 90% | PASS |
| **Mean Reciprocal Rank (MRR)** | `0.971` | >= 0.70 | PASS |

## 🛡️ Generation Quality & Cost Safety

| Metric | Value | Target Goal | Status |
|---|---|---|---|
| **Faithfulness Score** | `88.67%` | >= 90% | PASS |
| **Not-Found Accuracy** | `100.0%` | 100% | PASS |
| **Citation Accuracy** | `100.0%` | >= 95% | PASS |

## ⚡ Performance, Latency & Spend

* **Median Latency (p50):** `2.5 ms`
* **95th Percentile Latency (p95):** `4.5 ms`
* **Cohere API Calls:** 0 Embed + 0 Rerank
* **Total Tokens Generated:** 2496
* **Total Test Cost:** `$0.0002 USD`
