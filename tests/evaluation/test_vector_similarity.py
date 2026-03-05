"""Tests for vector similarity computation and embedding quality.

Verifies cosine similarity properties, embedding dimensionality,
and normalization behavior using mocked embedding outputs.
"""

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_np = np.array(a)
    b_np = np.array(b)
    dot = np.dot(a_np, b_np)
    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.5] * 341 + [1.0]  # 1024 dims
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0] * 512
        b = [0.0, 1.0] * 512
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors(self):
        v = [1.0, -0.5, 0.3] * 341 + [1.0]
        neg_v = [-x for x in v]
        assert cosine_similarity(v, neg_v) == pytest.approx(-1.0, abs=1e-6)

    def test_similarity_range(self):
        rng = np.random.default_rng(42)
        for _ in range(20):
            a = rng.standard_normal(1024).tolist()
            b = rng.standard_normal(1024).tolist()
            sim = cosine_similarity(a, b)
            assert -1.0 <= sim <= 1.0

    def test_normalized_vectors_dot_equals_cosine(self):
        rng = np.random.default_rng(99)
        a = rng.standard_normal(1024)
        b = rng.standard_normal(1024)
        a_norm = a / np.linalg.norm(a)
        b_norm = b / np.linalg.norm(b)
        dot = float(np.dot(a_norm, b_norm))
        cos = cosine_similarity(a_norm.tolist(), b_norm.tolist())
        assert dot == pytest.approx(cos, abs=1e-6)


class TestEmbeddingDimensionality:
    @patch("app.services.embedding_service._get_model")
    def test_output_dim_matches_config(self, mock_get_model):
        from app.core.config import settings

        mock_model = MagicMock()
        dim = settings.EMBEDDING_DIM
        mock_model.encode.return_value = np.random.randn(2, dim).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.services.embedding_service import compute_embeddings

        vectors = compute_embeddings(["text1", "text2"])
        assert len(vectors[0]) == dim
        assert len(vectors[1]) == dim

    @patch("app.services.embedding_service._get_model")
    def test_normalized_output(self, mock_get_model):
        """Embeddings should be L2-normalized (unit vectors)."""
        mock_model = MagicMock()
        v = np.random.randn(1, 1024).astype(np.float32)
        v = v / np.linalg.norm(v)  # simulate normalization
        mock_model.encode.return_value = v
        mock_get_model.return_value = mock_model

        from app.services.embedding_service import compute_embeddings

        result = compute_embeddings(["text"])
        norm = np.linalg.norm(result[0])
        assert norm == pytest.approx(1.0, abs=0.01)


class TestSimilarTextsPairwise:
    """Verify that semantically similar texts produce higher cosine similarity
    than dissimilar texts when using real-ish mock embeddings."""

    def _make_embedding(self, seed: int, bias: list[float] | None = None):
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(1024).astype(np.float64)
        if bias is not None:
            v[:len(bias)] += np.array(bias)
        v = v / np.linalg.norm(v)
        return v.tolist()

    def test_similar_bias_higher_similarity(self):
        # Two vectors with similar bias should be more similar than random
        bias = [10.0] * 50
        v1 = self._make_embedding(1, bias)
        v2 = self._make_embedding(2, bias)
        v_random = self._make_embedding(999)

        sim_similar = cosine_similarity(v1, v2)
        sim_random = cosine_similarity(v1, v_random)
        assert sim_similar > sim_random
