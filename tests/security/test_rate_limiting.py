"""Tests for the sliding-window rate limiter."""

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.auth import AuthenticatedKey
from app.core.rate_limit import check_rate_limit
from app.models.api_key import ApiKey


def _make_auth(rate_limit: int = 60) -> AuthenticatedKey:
    key = MagicMock(spec=ApiKey)
    key.id = uuid.uuid4()
    key.org_id = uuid.uuid4()
    key.collection_id = uuid.uuid4()
    key.scope = "search"
    key.rate_limit = rate_limit
    return AuthenticatedKey(key)


@pytest.fixture
def mock_request():
    return MagicMock()


@pytest.fixture
def mock_response():
    resp = MagicMock()
    resp.headers = {}
    return resp


class TestRateLimiting:
    @patch("app.core.rate_limit.settings")
    @patch("app.core.rate_limit.get_redis")
    async def test_under_limit_passes(self, mock_get_redis, mock_settings, mock_request, mock_response):
        mock_settings.RATE_LIMIT_ENABLED = True
        auth = _make_auth(rate_limit=100)

        mock_redis = AsyncMock()
        pipe = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, None, 5, None])  # count=5
        mock_redis.pipeline.return_value = pipe
        mock_get_redis.return_value = mock_redis

        result = await check_rate_limit(mock_request, mock_response, auth=auth)
        assert result is auth
        assert mock_response.headers["X-RateLimit-Limit"] == "100"
        assert mock_response.headers["X-RateLimit-Remaining"] == "95"

    @patch("app.core.rate_limit.settings")
    @patch("app.core.rate_limit.get_redis")
    async def test_over_limit_raises_429(self, mock_get_redis, mock_settings, mock_request, mock_response):
        mock_settings.RATE_LIMIT_ENABLED = True
        auth = _make_auth(rate_limit=10)

        mock_redis = AsyncMock()
        pipe = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, None, 15, None])  # count=15 > limit=10
        mock_redis.pipeline.return_value = pipe
        mock_get_redis.return_value = mock_redis

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(mock_request, mock_response, auth=auth)
        assert exc_info.value.status_code == 429

    @patch("app.core.rate_limit.settings")
    async def test_rate_limit_disabled(self, mock_settings, mock_request, mock_response):
        mock_settings.RATE_LIMIT_ENABLED = False
        auth = _make_auth(rate_limit=1)

        result = await check_rate_limit(mock_request, mock_response, auth=auth)
        assert result is auth

    @patch("app.core.rate_limit.settings")
    @patch("app.core.rate_limit.get_redis")
    async def test_headers_always_set(self, mock_get_redis, mock_settings, mock_request, mock_response):
        mock_settings.RATE_LIMIT_ENABLED = True
        auth = _make_auth(rate_limit=50)

        mock_redis = AsyncMock()
        pipe = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, None, 1, None])
        mock_redis.pipeline.return_value = pipe
        mock_get_redis.return_value = mock_redis

        await check_rate_limit(mock_request, mock_response, auth=auth)
        assert "X-RateLimit-Limit" in mock_response.headers
        assert "X-RateLimit-Remaining" in mock_response.headers
        assert "X-RateLimit-Reset" in mock_response.headers

    @patch("app.core.rate_limit.settings")
    @patch("app.core.rate_limit.get_redis")
    async def test_remaining_never_negative(self, mock_get_redis, mock_settings, mock_request, mock_response):
        mock_settings.RATE_LIMIT_ENABLED = True
        auth = _make_auth(rate_limit=5)

        mock_redis = AsyncMock()
        pipe = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, None, 3, None])
        mock_redis.pipeline.return_value = pipe
        mock_get_redis.return_value = mock_redis

        await check_rate_limit(mock_request, mock_response, auth=auth)
        remaining = int(mock_response.headers["X-RateLimit-Remaining"])
        assert remaining >= 0
