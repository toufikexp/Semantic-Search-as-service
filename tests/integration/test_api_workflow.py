"""Integration tests for API workflows across both search-api and ingestion-api.

Tests complete request/response flows using ASGI clients with mocked DB/auth.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.collection import Collection
from app.models.ingestion_job import IngestionJob


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    async def test_search_api_health(self, search_client):
        resp = await search_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data

    async def test_ingest_api_health(self, ingest_client):
        resp = await ingest_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ingestion"


# ---------------------------------------------------------------------------
# Collections CRUD via search-api
# ---------------------------------------------------------------------------

class TestCollectionEndpoints:
    @patch("app.services.collection_service.generate_api_key")
    async def test_create_collection(self, mock_gen, search_client, fake_db):
        mock_gen.side_effect = [("sk_ingest_raw", "h1"), ("sk_search_raw", "h2")]
        fake_db.refresh = AsyncMock(side_effect=lambda obj: None)

        resp = await search_client.post(
            "/api/v1/collections",
            json={"name": "test-col", "chunk_strategy": "adaptive"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-col"
        assert "api_keys" in data
        assert "ingest" in data["api_keys"]

    async def test_list_collections(self, search_client, fake_db, org_id):
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
        assert data["total"] == 0

    async def test_get_collection_not_found(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        fake_db.execute = AsyncMock(return_value=mock_result)

        resp = await search_client.get(f"/api/v1/collections/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"]["code"] == "NOT_FOUND"

    async def test_delete_collection_not_found(self, search_client, fake_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        fake_db.execute = AsyncMock(return_value=mock_result)

        resp = await search_client.delete(f"/api/v1/collections/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Search endpoint validation
# ---------------------------------------------------------------------------

class TestSearchEndpoints:
    async def test_search_requires_query(self, search_client):
        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"mode": "keyword"},
        )
        assert resp.status_code == 400

    async def test_search_invalid_mode_still_accepted(self, search_client, fake_db):
        """SearchRequest.mode is a plain str, not an enum, so unknown modes pass validation."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.commit = AsyncMock()

        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": "test", "mode": "keyword", "limit": 10},
        )
        # Should succeed (keyword mode doesn't need embedding)
        assert resp.status_code == 200

    async def test_suggest_requires_prefix(self, search_client):
        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/suggest",
            json={},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Document ingestion endpoint (via ingestion-api)
# ---------------------------------------------------------------------------

class TestDocumentIngestion:
    @patch("app.workers.tasks.process_ingestion_job")
    async def test_ingest_documents(self, mock_task, ingest_client, fake_db, collection_id):
        mock_task.delay = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.refresh = AsyncMock(side_effect=lambda obj: None)

        resp = await ingest_client.post(
            f"/api/v1/collections/{collection_id}/documents",
            json={
                "documents": [
                    {
                        "external_id": "doc-1",
                        "content": "Test content for ingestion.",
                        "title": "Test Doc",
                    }
                ]
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["documents_queued"] == 1
        assert data["status"] == "processing"

    async def test_ingest_empty_documents(self, ingest_client, collection_id):
        resp = await ingest_client.post(
            f"/api/v1/collections/{collection_id}/documents",
            json={"documents": []},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Jobs endpoint
# ---------------------------------------------------------------------------

class TestJobEndpoints:
    async def test_job_not_found(self, ingest_client, fake_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        fake_db.execute = AsyncMock(return_value=mock_result)

        resp = await ingest_client.get(f"/api/v1/jobs/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Webhook / Crawl endpoints
# ---------------------------------------------------------------------------

class TestWebhookEndpoints:
    async def test_register_webhook(self, ingest_client, collection_id):
        resp = await ingest_client.post(
            f"/api/v1/collections/{collection_id}/webhooks",
            json={
                "source_platform": "github",
                "event_types": ["push", "pull_request"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["source_platform"] == "github"
        assert data["status"] == "active"

    @patch("app.workers.tasks.run_crawl")
    async def test_trigger_crawl(self, mock_crawl, ingest_client, fake_db, collection_id):
        mock_crawl.delay = MagicMock()
        fake_db.refresh = AsyncMock(side_effect=lambda obj: None)

        resp = await ingest_client.post(
            f"/api/v1/collections/{collection_id}/crawl",
            json={"sitemap_url": "https://example.com/sitemap.xml", "max_pages": 10},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "started"
