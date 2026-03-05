"""Factory helpers for creating test objects without touching the database."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.core.auth import AuthenticatedKey
from app.models.api_key import ApiKey
from app.schemas.search import SearchRequest, SearchResult


def make_auth(
    scope: str = "master",
    org_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    rate_limit: int = 600,
) -> AuthenticatedKey:
    """Build an AuthenticatedKey without database access."""
    api_key = MagicMock(spec=ApiKey)
    api_key.id = uuid.uuid4()
    api_key.org_id = org_id or uuid.uuid4()
    api_key.collection_id = collection_id
    api_key.scope = scope
    api_key.rate_limit = rate_limit
    api_key.is_active = True
    return AuthenticatedKey(api_key)


def make_search_request(
    query: str = "test query",
    mode: str = "hybrid",
    limit: int = 20,
    offset: int = 0,
    highlight: bool = True,
    facets: list[str] | None = None,
    min_score: float = 0.0,
) -> SearchRequest:
    return SearchRequest(
        query=query,
        mode=mode,
        limit=limit,
        offset=offset,
        highlight=highlight,
        facets=facets or [],
        min_score=min_score,
    )


def make_search_result(
    external_id: str = "doc-1",
    score: float = 0.95,
    title: str | None = "Test Document",
    url: str | None = None,
    highlights: list[str] | None = None,
    metadata: dict | None = None,
) -> SearchResult:
    return SearchResult(
        doc_id=uuid.uuid4(),
        external_id=external_id,
        score=score,
        title=title,
        url=url,
        highlights=highlights or [],
        metadata=metadata or {},
    )


def make_collection_id() -> uuid.UUID:
    return uuid.uuid4()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
