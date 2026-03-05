"""Tests for embedding_service — model loading, compute_embeddings, caching."""

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestModelNameMapping:
    """Verify the alias -> HuggingFace model name resolution."""

    def test_known_aliases(self):
        from app.services.embedding_service import _get_model

        # We don't actually load the model in unit tests, just verify the map
        # exists and is correct by importing the module.
        import app.services.embedding_service as mod

        # Reset global so we can inspect without loading
        original = mod._model
        try:
            expected = {
                "bge-m3": "BAAI/bge-m3",
                "multilingual-e5-large": "intfloat/multilingual-e5-large",
                "nomic-embed-text-v1.5": "nomic-ai/nomic-embed-text-v1.5",
            }
            # Verify the mapping is inside _get_model by inspecting source
            import inspect
            source = inspect.getsource(mod._get_model)
            for alias, full_name in expected.items():
                assert alias in source
                assert full_name in source
        finally:
            mod._model = original


class TestComputeEmbeddings:
    """Test compute_embeddings with a mocked SentenceTransformer."""

    @patch("app.services.embedding_service._get_model")
    def test_returns_list_of_lists(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(3, 1024).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.services.embedding_service import compute_embeddings

        result = compute_embeddings(["text1", "text2", "text3"])
        assert len(result) == 3
        assert len(result[0]) == 1024
        assert all(isinstance(v, float) for v in result[0])

    @patch("app.services.embedding_service._get_model")
    def test_normalization_flag(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.ones((1, 1024), dtype=np.float32)
        mock_get_model.return_value = mock_model

        from app.services.embedding_service import compute_embeddings

        compute_embeddings(["test"])
        call_kwargs = mock_model.encode.call_args[1]
        assert call_kwargs["normalize_embeddings"] is True

    @patch("app.services.embedding_service._get_model")
    def test_batch_size_passed(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.ones((1, 1024), dtype=np.float32)
        mock_get_model.return_value = mock_model

        from app.services.embedding_service import compute_embeddings

        compute_embeddings(["test"])
        call_kwargs = mock_model.encode.call_args[1]
        assert "batch_size" in call_kwargs

    @patch("app.services.embedding_service._get_model")
    def test_empty_input(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.empty((0, 1024), dtype=np.float32)
        mock_get_model.return_value = mock_model

        from app.services.embedding_service import compute_embeddings

        result = compute_embeddings([])
        assert result == []


class TestGetQueryEmbedding:
    """Test the async cache-then-celery path of get_query_embedding."""

    @patch("app.services.embedding_service.redis")
    async def test_returns_cached_vector(self, mock_redis_module):
        mock_redis = MagicMock()
        expected = [0.1] * 1024
        mock_redis.get.return_value = json.dumps(expected)
        mock_redis_module.Redis.from_url.return_value = mock_redis

        from app.services.embedding_service import get_query_embedding

        result = await get_query_embedding("test query")
        assert result == expected
        mock_redis.get.assert_called_once()

    @patch("app.services.embedding_service.redis")
    @patch("app.workers.tasks.compute_query_embedding")
    async def test_dispatches_to_celery_on_cache_miss(self, mock_task, mock_redis_module):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis_module.Redis.from_url.return_value = mock_redis

        expected = [0.2] * 1024
        mock_async_result = MagicMock()
        mock_async_result.get.return_value = expected
        mock_task.delay.return_value = mock_async_result

        from app.services.embedding_service import get_query_embedding

        result = await get_query_embedding("new query")
        assert result == expected
        mock_task.delay.assert_called_once_with("new query")
        mock_redis.setex.assert_called_once()
