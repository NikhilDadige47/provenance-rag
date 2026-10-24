# Adding a New Provider to Provenance RAG

This guide explains how to add a new document parser or BYOK LLM provider while preserving the project's zero-secret persistence and egress security guarantees.

---

## 1. Adding a New Document Parser

Every document parser must normalize vendor output into the unified `StructuredDoc` / `Block` schema so chunking and retrieval remain provider-agnostic.

### Step 1: Implement `IParser` and Normalizer
Create `src/ingest/parsers/<provider_name>.py`:
```python
from pathlib import Path
from src.interfaces import IParser
from src.ingest.parsers.structured_doc import StructuredDoc, Block, BlockType
from src.security.secret import Secret
from src.security.egress import create_secure_client

class MyParserAdapter(IParser):
    @property
    def name(self) -> str:
        return "my_parser"

    @property
    def requires_key(self) -> bool:
        return True  # or False for free local parsers

    async def parse(self, file_path: Path, api_key: Secret | None = None) -> StructuredDoc:
        # 1. Use create_secure_client() for outbound calls
        # 2. Never log or store api_key
        # 3. Convert vendor response to Block objects
        # 4. Return StructuredDoc
        ...
```

### Step 2: Register in `ParserRegistry`
In `src/ingest/parsers/registry.py`:
```python
from src.ingest.parsers.<provider_name> import MyParserAdapter

# In ParserRegistry.__init__:
self.register(MyParserAdapter())
```

### Step 3: Authorize Upstream Host in Egress Allowlist
In `src/security/egress.py`, add the provider's domain to `ALLOWED_EGRESS_HOSTS`:
```python
ALLOWED_EGRESS_HOSTS = frozenset({
    ...,
    "api.myprovider.com",
})
```

### Step 4: Add Probe Endpoint to `connections.py`
In `src/api/connections.py`, map the provider to its cheapest, non-credit-consuming validation endpoint in `PROVIDER_PROBE_URLS`.

### Step 5: Save Test Fixture & Add Normalizer Tests
Save a sample vendor JSON/Markdown payload under `tests/fixtures/` and add test cases in `tests/ingest/test_normalizers.py`.

---

## 2. Adding a BYOK LLM Provider

BYOK LLM providers are called with request-scoped visitor keys passed in HTTP headers.

### Step 1: Implement `ILLM`
Create `src/generation/<provider_name>.py` implementing `ILLM.generate_stream(prompt, api_key, model)`.

### Step 2: Register in Provider Catalog
In `src/security/catalog.py` (or catalog config), add the provider name, docs link, recommended models, and context window limits.

### Step 3: Authorize Upstream Host
Add the API hostname to `ALLOWED_EGRESS_HOSTS` in `src/security/egress.py`.

### Step 4: Add Probe Endpoint
In `src/api/connections.py`, add a tiny completion/models check URL to `PROVIDER_PROBE_URLS`.
