"""Performance-oriented tests — latency budgets, concurrency, throughput.

These tests verify performance characteristics using mocked infrastructure.
They measure response times and verify that the system handles concurrent
requests without errors.
"""

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestResponseLatency:
    """Verify that API endpoints respond within reasonable time budgets."""

    async def test_health_under_100ms(self, search_client):
        start = time.monotonic()
        resp = await search_client.get("/health")
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert elapsed < 0.1, f"Health check took {elapsed:.3f}s, expected < 100ms"

    async def test_keyword_search_under_500ms(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.commit = AsyncMock()

        start = time.monotonic()
        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": "test", "mode": "keyword"},
        )
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert elapsed < 0.5, f"Search took {elapsed:.3f}s, expected < 500ms"

    async def test_suggest_under_200ms(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)

        start = time.monotonic()
        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/suggest",
            json={"prefix": "tes"},
        )
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert elapsed < 0.2, f"Suggest took {elapsed:.3f}s, expected < 200ms"

    async def test_list_collections_under_300ms(self, search_client, fake_db):
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        list_result.scalars.return_value = scalars
        fake_db.execute = AsyncMock(side_effect=[count_result, list_result])

        start = time.monotonic()
        resp = await search_client.get("/api/v1/collections")
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert elapsed < 0.3


class TestConcurrentRequests:
    """Verify the API handles concurrent requests without errors."""

    async def test_concurrent_health_checks(self, search_client):
        async def check():
            return await search_client.get("/health")

        results = await asyncio.gather(*[check() for _ in range(20)])
        assert all(r.status_code == 200 for r in results)

    async def test_concurrent_search_requests(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.commit = AsyncMock()

        async def search():
            return await search_client.post(
                f"/api/v1/collections/{uuid.uuid4()}/search",
                json={"query": "concurrent test", "mode": "keyword"},
            )

        results = await asyncio.gather(*[search() for _ in range(10)])
        assert all(r.status_code == 200 for r in results)

    async def test_concurrent_suggest_requests(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)

        async def suggest():
            return await search_client.post(
                f"/api/v1/collections/{uuid.uuid4()}/suggest",
                json={"prefix": "test"},
            )

        results = await asyncio.gather(*[suggest() for _ in range(10)])
        assert all(r.status_code == 200 for r in results)


class TestTookMsAccuracy:
    """Verify the took_ms field in search responses is reasonable."""

    async def test_took_ms_positive(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.commit = AsyncMock()

        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": "timing test", "mode": "keyword"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["took_ms"] >= 0

    async def test_took_ms_under_budget(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.commit = AsyncMock()

        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": "timing", "mode": "keyword"},
        )
        data = resp.json()
        # With mocked DB, should be very fast
        assert data["took_ms"] < 1000


class TestChunkingPerformance:
    """Verify chunking service handles large documents efficiently."""

    def test_large_document_chunking_time(self):
        from app.services.chunking_service import chunk_text

        # 100KB document
        content = "This is a test paragraph with meaningful content. " * 2000
        start = time.monotonic()
        chunks = chunk_text(content, strategy="adaptive", chunk_size=512)
        elapsed = time.monotonic() - start

        assert len(chunks) > 0
        assert elapsed < 5.0, f"Chunking 100KB took {elapsed:.3f}s, expected < 5s"

    def test_many_paragraphs_chunking_time(self):
        from app.services.chunking_service import chunk_text

        paragraphs = ["Paragraph number %d with some content." % i for i in range(500)]
        content = "\n\n".join(paragraphs)

        start = time.monotonic()
        chunks = chunk_text(content, strategy="paragraph", chunk_size=128)
        elapsed = time.monotonic() - start

        assert len(chunks) > 0
        assert elapsed < 5.0
