# Provenance RAG: Phase 7 Benchmark Evaluation Report

**Date:** 2026-10-27 04:05:29 UTC  
**Total Benchmark Queries:** 50  

## 🎯 Retrieval & Ranking Performance

| Metric | Value | Target Goal | Status |
|---|---|---|---|
| **Recall@5** | `51.43%` | >= 85% | WARN |
| **Recall@10** | `51.43%` | >= 90% | WARN |
| **Mean Reciprocal Rank (MRR)** | `0.514` | >= 0.70 | WARN |

## 🛡️ Generation Quality & Cost Safety

| Metric | Value | Target Goal | Status |
|---|---|---|---|
| **Faithfulness Score** | `7.17%` | >= 90% | WARN |
| **Not-Found Accuracy** | `13.33%` | 100% | WARN |
| **Citation Accuracy** | `100.0%` | >= 95% | PASS |

## ⚡ Performance, Latency & Spend

* **Median Latency (p50):** `0.5 ms`
* **95th Percentile Latency (p95):** `1.5 ms`
* **Cohere API Calls:** 50 Embed + 0 Rerank
* **Total Tokens Generated:** 8640
* **Total Test Cost:** `$0.0014 USD`
