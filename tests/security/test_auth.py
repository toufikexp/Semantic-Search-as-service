"""Security tests for authentication, authorization, and scope enforcement."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.auth import AuthenticatedKey, get_api_key, require_scope
from app.core.security import hash_api_key
from app.models.api_key import ApiKey


# ---------------------------------------------------------------------------
# AuthenticatedKey
# ---------------------------------------------------------------------------

class TestAuthenticatedKey:
    def _make_key(self, scope: str, collection_id=None):
        key = MagicMock(spec=ApiKey)
        key.id = uuid.uuid4()
        key.org_id = uuid.uuid4()
        key.collection_id = collection_id
        key.scope = scope
        key.rate_limit = 600
        return AuthenticatedKey(key)

    def test_master_has_all_scopes(self):
        auth = self._make_key("master")
        assert auth.has_scope("master")
        assert auth.has_scope("ingest")
        assert auth.has_scope("search")

    def test_ingest_scope_limited(self):
        auth = self._make_key("ingest")
        assert auth.has_scope("ingest")
        assert not auth.has_scope("search")
        assert not auth.has_scope("master")

    def test_search_scope_limited(self):
        auth = self._make_key("search")
        assert auth.has_scope("search")
        assert not auth.has_scope("ingest")
        assert not auth.has_scope("master")

    def test_master_can_access_any_collection(self):
        auth = self._make_key("master")
        assert auth.can_access_collection(uuid.uuid4())

    def test_scoped_key_limited_to_own_collection(self):
        col_id = uuid.uuid4()
        auth = self._make_key("search", collection_id=col_id)
        assert auth.can_access_collection(col_id)
        assert not auth.can_access_collection(uuid.uuid4())

    def test_scoped_key_none_collection(self):
        auth = self._make_key("search", collection_id=None)
        # collection_id=None != random UUID
        assert not auth.can_access_collection(uuid.uuid4())


# ---------------------------------------------------------------------------
# get_api_key dependency
# ---------------------------------------------------------------------------

class TestGetApiKey:
    async def test_invalid_header_format(self):
        from fastapi import HTTPException

        request = MagicMock()
        db = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await get_api_key(request, authorization="InvalidFormat", db=db)
        assert exc_info.value.status_code == 401

    async def test_missing_bearer_prefix(self):
        from fastapi import HTTPException

        request = MagicMock()
        db = AsyncMock()
        with pytest.raises(HTTPException):
            await get_api_key(request, authorization="Token abc123", db=db)

    async def test_invalid_key(self):
        from fastapi import HTTPException

        request = MagicMock()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await get_api_key(request, authorization="Bearer invalid_key_123", db=db)
        assert exc_info.value.status_code == 401

    async def test_valid_key(self):
        request = MagicMock()
        db = AsyncMock()

        api_key = MagicMock(spec=ApiKey)
        api_key.id = uuid.uuid4()
        api_key.org_id = uuid.uuid4()
        api_key.collection_id = uuid.uuid4()
        api_key.scope = "search"
        api_key.rate_limit = 100
        api_key.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = api_key
        db.execute = AsyncMock(return_value=mock_result)

        auth = await get_api_key(request, authorization="Bearer valid_key", db=db)
        assert isinstance(auth, AuthenticatedKey)
        assert auth.scope == "search"

    async def test_inactive_key_rejected(self):
        from fastapi import HTTPException

        request = MagicMock()
        db = AsyncMock()
        # Query returns None (inactive keys filtered by WHERE clause)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await get_api_key(request, authorization="Bearer inactive_key", db=db)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# require_scope dependency factory
# ---------------------------------------------------------------------------

class TestRequireScope:
    async def test_master_passes_all_checks(self):
        key = MagicMock(spec=ApiKey)
        key.id = uuid.uuid4()
        key.org_id = uuid.uuid4()
        key.collection_id = None
        key.scope = "master"
        key.rate_limit = 600
        auth = AuthenticatedKey(key)

        check = require_scope("ingest")
        # Manually inject auth
        result = await check(auth=auth)
        assert result is auth

    async def test_wrong_scope_raises_403(self):
        from fastapi import HTTPException

        key = MagicMock(spec=ApiKey)
        key.id = uuid.uuid4()
        key.org_id = uuid.uuid4()
        key.collection_id = uuid.uuid4()
        key.scope = "search"
        key.rate_limit = 100
        auth = AuthenticatedKey(key)

        check = require_scope("ingest")
        with pytest.raises(HTTPException) as exc_info:
            await check(auth=auth)
        assert exc_info.value.status_code == 403

    async def test_matching_scope_passes(self):
        key = MagicMock(spec=ApiKey)
        key.id = uuid.uuid4()
        key.org_id = uuid.uuid4()
        key.collection_id = uuid.uuid4()
        key.scope = "search"
        key.rate_limit = 100
        auth = AuthenticatedKey(key)

        check = require_scope("search")
        result = await check(auth=auth)
        assert result is auth
