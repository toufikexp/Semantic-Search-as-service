"""API endpoint contract tests — request/response shape validation."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _populate_server_defaults(obj):
    """Simulate DB-generated defaults for server_default / default columns."""
    if getattr(obj, "id", None) is None:
        obj.id = uuid.uuid4()
    if hasattr(obj, "status") and getattr(obj, "status", None) is None:
        obj.status = "active"
    if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
        obj.created_at = datetime.now(timezone.utc)
    if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
        obj.updated_at = datetime.now(timezone.utc)


class TestCollectionAPIContract:
    @patch("app.services.collection_service.generate_api_key")
    async def test_create_response_shape(self, mock_gen, search_client, fake_db):
        mock_gen.side_effect = [("sk_ingest_raw", "h1"), ("sk_search_raw", "h2")]
        fake_db.refresh = AsyncMock(side_effect=_populate_server_defaults)

        resp = await search_client.post(
            "/api/v1/collections",
            json={"name": "contract-test"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert "name" in data
        assert "status" in data
        assert "api_keys" in data
        assert "created_at" in data

    async def test_list_response_shape(self, search_client, fake_db):
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        list_result.scalars.return_value = scalars
        fake_db.execute = AsyncMock(side_effect=[count_result, list_result])

        resp = await search_client.get("/api/v1/collections")
        assert resp.status_code == 200
        data = resp.json()
        assert "collections" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data


class TestSearchAPIContract:
    async def test_keyword_search_response_shape(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.commit = AsyncMock()

        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": "test", "mode": "keyword"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "facets" in data
        assert "total" in data
        assert "query_id" in data
        assert "took_ms" in data
        assert isinstance(data["results"], list)

    async def test_suggest_response_shape(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)

        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/suggest",
            json={"prefix": "tes"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)


class TestDocumentAPIContract:
    @patch("app.workers.tasks.process_ingestion_job")
    async def test_ingest_response_shape(self, mock_task, ingest_client, fake_db, collection_id):
        mock_task.delay = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.refresh = AsyncMock(side_effect=_populate_server_defaults)

        resp = await ingest_client.post(
            f"/api/v1/collections/{collection_id}/documents",
            json={
                "documents": [
                    {"external_id": "e1", "content": "Test content."}
                ]
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert "documents_queued" in data
        assert "status" in data


class TestWebhookAPIContract:
    async def test_webhook_response_shape(self, ingest_client, collection_id):
        resp = await ingest_client.post(
            f"/api/v1/collections/{collection_id}/webhooks",
            json={"source_platform": "github", "event_types": ["push"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert "collection_id" in data
        assert "source_platform" in data
        assert "event_types" in data
        assert "endpoint_url" in data
        assert "status" in data

    @patch("app.workers.tasks.run_crawl")
    async def test_crawl_response_shape(self, mock_crawl, ingest_client, fake_db, collection_id):
        mock_crawl.delay = MagicMock()
        fake_db.refresh = AsyncMock(side_effect=_populate_server_defaults)

        resp = await ingest_client.post(
            f"/api/v1/collections/{collection_id}/crawl",
            json={"sitemap_url": "https://example.com/sitemap.xml"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert "status" in data
        assert "pages_discovered" in data


class TestRequestValidation:
    """Test that invalid requests are properly rejected."""

    async def test_search_empty_query_rejected(self, search_client):
        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": "", "mode": "keyword"},
        )
        assert resp.status_code == 400

    async def test_search_limit_too_high(self, search_client):
        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": "test", "limit": 999},
        )
        assert resp.status_code == 400

    async def test_search_negative_offset(self, search_client):
        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": "test", "offset": -1},
        )
        assert resp.status_code == 400

    async def test_suggest_empty_prefix_rejected(self, search_client):
        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/suggest",
            json={"prefix": ""},
        )
        assert resp.status_code == 400

    async def test_collection_create_empty_name(self, search_client):
        resp = await search_client.post(
            "/api/v1/collections",
            json={"name": ""},
        )
        # Empty string should fail max_length or validation
        assert resp.status_code in (400, 422)

    async def test_ingest_no_documents(self, ingest_client, collection_id):
        resp = await ingest_client.post(
            f"/api/v1/collections/{collection_id}/documents",
            json={"documents": []},
        )
        assert resp.status_code == 400
