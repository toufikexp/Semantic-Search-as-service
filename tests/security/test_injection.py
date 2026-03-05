"""Security tests for injection attack vectors — SQL injection, XSS, header injection."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSQLInjectionVectors:
    """Verify that SQL injection payloads are safely handled by the API."""

    SQLI_PAYLOADS = [
        "'; DROP TABLE documents; --",
        "1 OR 1=1",
        "' UNION SELECT * FROM api_keys --",
        "1; DELETE FROM embeddings",
        "' OR ''='",
        "admin'--",
        "1' AND (SELECT COUNT(*) FROM api_keys) > 0 --",
    ]

    @pytest.mark.parametrize("payload", SQLI_PAYLOADS)
    async def test_search_query_sqli(self, search_client, fake_db, payload):
        """Search endpoint should handle SQL injection in query field safely."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.commit = AsyncMock()

        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": payload, "mode": "keyword"},
        )
        # Should not crash — either 200 with empty results or 400/422
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.parametrize("payload", SQLI_PAYLOADS)
    async def test_suggest_prefix_sqli(self, search_client, fake_db, payload):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)

        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/suggest",
            json={"prefix": payload},
        )
        assert resp.status_code in (200, 400, 422)


class TestXSSVectors:
    """Verify that XSS payloads in document content/titles don't break responses."""

    XSS_PAYLOADS = [
        "<script>alert('xss')</script>",
        '"><img src=x onerror=alert(1)>',
        "javascript:alert(document.cookie)",
        "<svg onload=alert(1)>",
        "{{constructor.constructor('return this')()}}"
    ]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    async def test_search_handles_xss_in_query(self, search_client, fake_db, payload):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)
        fake_db.commit = AsyncMock()

        resp = await search_client.post(
            f"/api/v1/collections/{uuid.uuid4()}/search",
            json={"query": payload, "mode": "keyword"},
        )
        assert resp.status_code in (200, 400, 422)


class TestPathTraversal:
    """Verify path traversal attempts are handled."""

    TRAVERSAL_PAYLOADS = [
        "../../../etc/passwd",
        "..%2F..%2F..%2Fetc%2Fpasswd",
        "....//....//etc/passwd",
    ]

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    async def test_collection_id_path_traversal(self, search_client, payload):
        resp = await search_client.get(f"/api/v1/collections/{payload}")
        # Should return 422 (invalid UUID) not 200 with file contents
        assert resp.status_code == 422

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    async def test_document_external_id_traversal(self, ingest_client, fake_db, payload):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        fake_db.execute = AsyncMock(return_value=mock_result)

        resp = await ingest_client.get(
            f"/api/v1/collections/{uuid.uuid4()}/documents/{payload}"
        )
        assert resp.status_code in (404, 422)


class TestHeaderInjection:
    """Verify that malicious authorization headers are handled safely."""

    async def test_newline_in_auth_header(self, search_client):
        resp = await search_client.get(
            "/api/v1/collections",
            headers={"Authorization": "Bearer test\r\nX-Injected: true"},
        )
        # Overridden auth means this might return 200, but the injection
        # should not cause a crash
        assert resp.status_code in (200, 400, 401, 422)

    async def test_very_long_auth_header(self, search_client):
        long_key = "Bearer " + "A" * 10000
        resp = await search_client.get(
            "/api/v1/collections",
            headers={"Authorization": long_key},
        )
        assert resp.status_code in (200, 400, 401, 422)


class TestCollectionAccessIsolation:
    """Verify that scoped keys cannot access other collections."""

    async def test_search_scoped_key_rejected_for_wrong_collection(
        self, search_client_scoped, fake_db, search_auth
    ):
        # search_auth is bound to a specific collection_id
        other_collection = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        fake_db.execute = AsyncMock(return_value=mock_result)

        resp = await search_client_scoped.post(
            f"/api/v1/collections/{other_collection}/search",
            json={"query": "test", "mode": "keyword"},
        )
        assert resp.status_code == 403
