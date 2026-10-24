"""Retrieval layer: dense embeddings, local sparse BM25, Qdrant store, reranker, and search."""

from src.retrieval.embed import CohereEmbedder
from src.retrieval.expansion import ContextExpander, ExpandedContextPassage, ExpansionResult
from src.retrieval.rerank import CohereReranker
from src.retrieval.search import HybridSearchPipeline, RetrievedChunk, SearchResult
from src.retrieval.sparse import LocalSparseVectorizer, SparseVector
from src.retrieval.store import QdrantVectorStore

__all__ = [
    "CohereEmbedder",
    "CohereReranker",
    "ContextExpander",
    "ExpandedContextPassage",
    "ExpansionResult",
    "HybridSearchPipeline",
    "LocalSparseVectorizer",
    "QdrantVectorStore",
    "RetrievedChunk",
    "SearchResult",
    "SparseVector",
]
