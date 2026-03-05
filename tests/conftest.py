"""Shared fixtures for the entire test suite.

Provides ASGI clients for both search-api and ingestion-api, mock auth
dependencies, and reusable database/redis fakes.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.auth import AuthenticatedKey, get_api_key
from app.core.database import get_db
from app.models.api_key import ApiKey


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

def _build_auth(scope: str, org_id: uuid.UUID, collection_id: uuid.UUID | None):
    key = MagicMock(spec=ApiKey)
    key.id = uuid.uuid4()
    key.org_id = org_id
    key.collection_id = collection_id
    key.scope = scope
    key.rate_limit = 600
    key.is_active = True
    return AuthenticatedKey(key)


@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def collection_id():
    return uuid.uuid4()


@pytest.fixture
def master_auth(org_id):
    return _build_auth("master", org_id, None)


@pytest.fixture
def ingest_auth(org_id, collection_id):
    return _build_auth("ingest", org_id, collection_id)


@pytest.fixture
def search_auth(org_id, collection_id):
    return _build_auth("search", org_id, collection_id)


# ---------------------------------------------------------------------------
# Fake async DB session
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_db():
    """A lightweight mock AsyncSession for unit tests."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# ASGI client for search-api (app.main:app)
# ---------------------------------------------------------------------------

@pytest.fixture
async def search_client(master_auth, fake_db):
    """AsyncClient wired to the search-api with auth and DB overridden."""
    from app.main import app

    async def _override_auth():
        return master_auth

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_api_key] = _override_auth
    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def search_client_scoped(search_auth, fake_db):
    """AsyncClient with search-scoped auth."""
    from app.main import app

    async def _override_auth():
        return search_auth

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_api_key] = _override_auth
    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# ASGI client for ingestion-api (app.ingest:app)
# ---------------------------------------------------------------------------

@pytest.fixture
async def ingest_client(master_auth, fake_db):
    """AsyncClient wired to the ingestion-api with auth and DB overridden."""
    from app.ingest import app

    async def _override_auth():
        return master_auth

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_api_key] = _override_auth
    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def ingest_client_scoped(ingest_auth, fake_db):
    """AsyncClient with ingest-scoped auth for ingestion-api."""
    from app.ingest import app

    async def _override_auth():
        return ingest_auth

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_api_key] = _override_auth
    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Unauthenticated client (no auth override — tests 401 paths)
# ---------------------------------------------------------------------------

@pytest.fixture
async def unauth_client():
    """AsyncClient with NO auth overrides — requests will fail auth."""
    from app.main import app

    app.dependency_overrides.pop(get_api_key, None)
    app.dependency_overrides.pop(get_db, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
