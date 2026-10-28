import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.retrieval.embed import INPUT_WINDOW_SECONDS, CohereEmbedder
from src.security.errors import InvalidKeyError, RateLimitedError
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
    from src.security.errors import ProviderUnavailableError

    embedder = CohereEmbedder(api_key=Secret("co-test-valid-key"))
    embedder._failure_count = 5
    embedder._circuit_open_until = time.time() + 60.0

    with pytest.raises(ProviderUnavailableError):
        await embedder.embed(["Immediate fail text"])


@pytest.mark.asyncio
async def test_embedder_waits_when_input_window_is_full():
    """Stay under Cohere's 2,000 inputs/min by waiting when the rolling window is full."""
    mock_vector = [0.1] * 1024
    embedder = CohereEmbedder(
        api_key=Secret("co-test-valid-key"),
        max_inputs_per_minute=200,
    )
    embedder._input_window.append((time.monotonic(), 200))
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": {"float": [mock_vector]}}

    with (
        patch.object(embedder._http_client, "post", new_callable=AsyncMock) as mock_post,
        patch("src.retrieval.embed.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_post.return_value = mock_response
        await embedder.embed(["one more chunk"])
        mock_sleep.assert_awaited()
        assert mock_sleep.await_args.args[0] >= INPUT_WINDOW_SECONDS - 1


@pytest.mark.asyncio
async def test_embedder_small_query_does_not_pace():
    mock_vector = [0.1] * 1024
    embedder = CohereEmbedder(api_key=Secret("co-test-valid-key"))
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": {"float": [mock_vector]}}

    with (
        patch.object(embedder._http_client, "post", new_callable=AsyncMock) as mock_post,
        patch("src.retrieval.embed.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_post.return_value = mock_response
        await embedder.embed(["search query"])
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_embedder_429_waits_then_succeeds():
    mock_vector = [0.1] * 1024
    embedder = CohereEmbedder(
        api_key=Secret("co-test-valid-key"),
        rate_limit_wait_seconds=60.0,
        max_retries=3,
    )
    limited = MagicMock()
    limited.status_code = 429
    limited.headers = {}
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {"embeddings": {"float": [mock_vector]}}

    with (
        patch.object(embedder._http_client, "post", new_callable=AsyncMock) as mock_post,
        patch("src.retrieval.embed.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_post.side_effect = [limited, ok]
        vectors = await embedder.embed(["one chunk"])
        assert len(vectors) == 1
        mock_sleep.assert_awaited()
        assert mock_sleep.await_args.args[0] == 60.0


@pytest.mark.asyncio
async def test_embedder_429_exhausted_raises_rate_limited():
    embedder = CohereEmbedder(
        api_key=Secret("co-test-valid-key"),
        rate_limit_wait_seconds=1.0,
        max_retries=2,
    )
    limited = MagicMock()
    limited.status_code = 429
    limited.headers = {}

    with (
        patch.object(embedder._http_client, "post", new_callable=AsyncMock) as mock_post,
        patch("src.retrieval.embed.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_post.return_value = limited
        with pytest.raises(RateLimitedError):
            await embedder.embed(["one chunk"])


def test_embedder_accepts_owner_config():
    """Verify embedder accepts OwnerConfig instance directly without AttributeError."""
    from src.security.config import OwnerConfig

    cfg = OwnerConfig(cohere_api_key="co-test-owner-key-12345", groq_api_key="test", qdrant_url=":memory:")
    embedder = CohereEmbedder(cfg)
    assert embedder._api_key is not None
    assert embedder._api_key.reveal() == "co-test-owner-key-12345"
