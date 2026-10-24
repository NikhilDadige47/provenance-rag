"""Tests for HybridSearchPipeline, scope filtering, and not-found gate."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.retrieval.search import HybridSearchPipeline


@pytest.mark.asyncio
async def test_search_pipeline_not_found_gate():
    """Verify not-found gate flags query as ungrounded when score < threshold."""
    mock_embedder = MagicMock()
    mock_embedder.embed = AsyncMock(return_value=[[0.1] * 1024])
    mock_embedder.dimension = 1024

    mock_store = MagicMock()
    mock_store.hybrid_search.return_value = [
        {
            "score": 0.10,
            "payload": {
                "chunk_id": "c1",
                "doc_id": "d1",
                "parent_id": "p1",
                "title": "Test Doc",
                "breadcrumb": "Sec 1",
                "page": 1,
                "display_text": "Low relevance chunk",
                "embedding_text": "Sec 1\n\nLow relevance chunk",
            },
        }
    ]

    mock_reranker = MagicMock()
    mock_reranker.rerank = AsyncMock(
        return_value=[
            {
                "index": 0,
                "text": "Sec 1\n\nLow relevance chunk",
                "relevance_score": 0.12,  # Below default 0.25 threshold
                "is_fallback": False,
            }
        ]
    )

    pipeline = HybridSearchPipeline(
        embedder=mock_embedder,
        store=mock_store,
        reranker=mock_reranker,
        not_found_threshold=0.25,
    )

    result = await pipeline.search("obscure impossible question", scope="demo")
    assert result.is_found is False
    assert result.reason == "below_relevance_threshold"


@pytest.mark.asyncio
async def test_search_pipeline_success():
    """Verify search pipeline passes when score >= threshold."""
    mock_embedder = MagicMock()
    mock_embedder.embed = AsyncMock(return_value=[[0.1] * 1024])
    mock_embedder.dimension = 1024

    mock_store = MagicMock()
    mock_store.hybrid_search.return_value = [
        {
            "score": 0.85,
            "payload": {
                "chunk_id": "c1",
                "doc_id": "d1",
                "parent_id": "p1",
                "title": "Financial Report",
                "breadcrumb": "Revenue",
                "page": 2,
                "display_text": "Revenue grew by 24%",
                "embedding_text": "Revenue\n\nRevenue grew by 24%",
            },
        }
    ]

    mock_reranker = MagicMock()
    mock_reranker.rerank = AsyncMock(
        return_value=[
            {
                "index": 0,
                "text": "Revenue\n\nRevenue grew by 24%",
                "relevance_score": 0.89,
                "is_fallback": False,
            }
        ]
    )

    pipeline = HybridSearchPipeline(
        embedder=mock_embedder,
        store=mock_store,
        reranker=mock_reranker,
        not_found_threshold=0.25,
    )

    result = await pipeline.search("What was revenue growth?", scope="demo")
    assert result.is_found is True
    assert len(result.chunks) == 1
    assert result.chunks[0].title == "Financial Report"
    assert result.chunks[0].score == 0.89
