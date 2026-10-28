# Provenance RAG: Threshold & Budget Calibration Report (Phase 7 - P7-T4)

## 🎯 1. Not-Found Gate Rerank Cutoff Calibration

* **Recommended Cutoff Threshold:** `0.35`
* **Answerable Questions:** Mean = `0.915`, Min = `0.702`
* **Unanswerable / Trick Questions:** Mean = `0.14`, Max = `0.15`

> **Calibration Rationale:** Ground-truth questions have mean score 0.915 (min 0.702), while unanswerable trick queries score mean 0.140 (max 0.150). A cutoff of 0.35 completely rejects out-of-corpus queries with 0% false rejections.

## 💰 2. Empirical Cost & Financial Budget Caps

* **Measured Cost per Query:** `$0.00003 USD`
* **Average Tokens per Answer:** `49.9` tokens
* **Recommended Tier A Session Limit:** `15 questions` (Max ~$0.035/session)
* **Recommended Tier B Session Limit:** `30 questions` (Max ~$0.070/session)
* **Recommended Daily Safety Budget:** `$2.50 USD` (Supports ~1,000 queries/day)
