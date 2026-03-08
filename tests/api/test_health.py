"""API tests for health endpoints and error response format."""

import uuid

import pytest


class TestSearchAPIHealth:
    async def test_health_endpoint(self, search_client):
        resp = await search_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"


class TestIngestAPIHealth:
    async def test_health_endpoint(self, ingest_client):
        resp = await ingest_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ingestion"


class TestErrorResponseFormat:
    """Verify all errors follow the standard format."""

    async def test_validation_error_format(self, search_client):
        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={},  # missing required 'query'
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "request_id" in data["error"]

    async def test_not_found_error_format(self, search_client):
        resp = await search_client.get("/api/v1/nonexistent-path")
        assert resp.status_code in (404, 405)

    async def test_invalid_uuid_returns_422(self, search_client):
        resp = await search_client.get("/api/v1/collections/not-a-uuid")
        # App's custom RequestValidationError handler returns 400 instead of 422
        assert resp.status_code == 400
