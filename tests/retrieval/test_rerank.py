"""Unit and integration tests for CohereReranker adapter and fallback behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.retrieval.rerank import CohereReranker
from src.security.secret import Secret


@pytest.mark.asyncio
async def test_rerank_success_orders_by_relevance():
    """Verify reranker returns candidates ordered by relevance score."""
    reranker = CohereReranker(api_key=Secret("co-test-rerank-key"))

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"index": 2, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.81},
        ]
    }

    docs = ["First doc", "Second doc", "Third doc"]
    with patch.object(reranker._http_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        results = await reranker.rerank("test query", docs, top_n=2)

        assert len(results) == 2
        assert results[0]["index"] == 2
        assert results[0]["text"] == "Third doc"
        assert results[0]["relevance_score"] == 0.95
        assert results[0]["is_fallback"] is False


@pytest.mark.asyncio
async def test_rerank_fallback_on_outage():
    """Verify reranker gracefully falls back to hybrid order when provider errors."""
    reranker = CohereReranker(api_key=Secret("co-test-rerank-key"))

    with patch.object(reranker._http_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = Exception("Connection timed out")
        docs = ["Doc A", "Doc B", "Doc C"]
        results = await reranker.rerank("query", docs, top_n=2)

        assert len(results) == 2
        assert results[0]["index"] == 0
        assert results[0]["text"] == "Doc A"
        assert results[0]["is_fallback"] is True
        assert results[1]["index"] == 1
        assert results[1]["text"] == "Doc B"


@pytest.mark.asyncio
async def test_rerank_usage_callback():
    """Verify usage callback is invoked on successful rerank call."""
    recorded_counts = []
    reranker = CohereReranker(
        api_key=Secret("co-test-rerank-key"),
        usage_callback=lambda count: recorded_counts.append(count),
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": [{"index": 0, "relevance_score": 0.9}]}

    with patch.object(reranker._http_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        await reranker.rerank("query", ["Doc 1", "Doc 2"], top_n=1)
        assert recorded_counts == [1]
