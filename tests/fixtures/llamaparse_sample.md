# System Architecture Overview

This document outlines the core architecture of the hybrid RAG system.

| Component | Status | Latency |
|---|---|---|
| Local Parser | Ready | < 50ms |
| Chunking Engine | Active | < 20ms |
| Cohere Embed | Online | ~120ms |
| Vector Store | Active | ~15ms |

- Key Safety: Zero credential persistence
- Isolation: Multi-tenant scope filtering
- Egress: Strict provider firewall

--- [Page 2] ---

## Core Retrieval Pipeline

Detailed algorithmic steps for two-stage retrieval and answer grounding.

```python
def retrieve_candidates(query: str, scope: str) -> list[dict]:
    # Hybrid search fusing dense and sparse representations
    return store.hybrid_search(dense_vec, sparse_vec, scope=scope)
```

Additional details regarding parent window expansion and citation verification.
