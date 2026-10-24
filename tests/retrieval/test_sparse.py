"""Unit tests for the local sparse vectorizer."""

from src.retrieval.sparse import LocalSparseVectorizer


def test_sparse_vectorizer_basic():
    """Verify sparse vectorizer outputs valid indices and weights."""
    vectorizer = LocalSparseVectorizer()
    vec = vectorizer.vectorize("Revenue increased by 15 percent in Q3.")

    assert len(vec.indices) > 0
    assert len(vec.values) == len(vec.indices)
    assert all(val > 0 for val in vec.values)

    # Conversion to Qdrant dict
    d = vec.as_dict()
    assert "indices" in d
    assert "values" in d


def test_sparse_vectorizer_deterministic():
    """Verify identical texts produce identical indices and values."""
    vectorizer = LocalSparseVectorizer()
    text = "Provenance RAG guarantees key safety and egress firewalling."

    vec1 = vectorizer.vectorize(text)
    vec2 = vectorizer.vectorize(text)

    assert vec1.indices == vec2.indices
    assert vec1.values == vec2.values


def test_sparse_vectorizer_empty():
    """Verify empty text returns empty sparse vector."""
    vectorizer = LocalSparseVectorizer()
    vec = vectorizer.vectorize("")
    assert len(vec.indices) == 0
    assert len(vec.values) == 0
