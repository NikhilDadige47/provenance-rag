from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.retrieval.embed import CohereEmbedder
from src.security.errors import InvalidKeyError
from src.security.secret import Secret


@pytest.mark.asyncio
async def test_embedder_missing_key_raises():
    """Verify embedder raises InvalidKeyError when API key is missing."""
    embedder = CohereEmbedder(api_key=Secret(""))
    with pytest.raises(InvalidKeyError):
        await embedder.embed(["Sample document text"])


@pytest.mark.asyncio
async def test_embedder_batch_embedding_success():
    """Verify embedder correctly calls Cohere API and returns 1024-dim vectors."""
    mock_vector = [0.1] * 1024
    recorded_counts = []

    def mock_usage(count: int):
        recorded_counts.append(count)

    embedder = CohereEmbedder(
        api_key=Secret("co-test-valid-key-12345"),
        usage_callback=mock_usage,
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": {"float": [mock_vector, mock_vector]}}

    with patch.object(embedder._http_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        vectors = await embedder.embed(["Doc chunk 1", "Doc chunk 2"], input_type="search_document")
        assert len(vectors) == 2
        assert len(vectors[0]) == 1024
        assert recorded_counts == [2]


@pytest.mark.asyncio
async def test_embedder_circuit_breaker_tripping():
    """Verify circuit breaker trips and fails fast after repeated failures."""
    import time

    from src.security.errors import ProviderUnavailableError

    embedder = CohereEmbedder(api_key=Secret("co-test-valid-key"))
    embedder._failure_count = 5
    embedder._circuit_open_until = time.time() + 60.0

    with pytest.raises(ProviderUnavailableError):
        await embedder.embed(["Immediate fail text"])
