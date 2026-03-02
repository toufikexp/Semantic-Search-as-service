import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedKey, require_scope
from app.core.database import get_db
from app.schemas.search import (
    SearchRequest,
    SearchResponse,
    SuggestRequest,
    SuggestResponse,
)
from app.services import search_service

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_collection(
    collection_id: uuid.UUID,
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(require_scope("search")),
):
    """Execute a search query against a collection."""
    if not auth.can_access_collection(collection_id):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "API key does not have access to this collection",
                }
            },
        )

    # Generate query embedding for semantic/hybrid search
    query_vector = None
    if body.mode in ("semantic", "hybrid"):
        from app.services.embedding_service import get_query_embedding

        query_vector = await get_query_embedding(body.query)

    return await search_service.execute_search(
        db, collection_id, body, query_vector
    )


@router.post("/suggest", response_model=SuggestResponse)
async def suggest(
    collection_id: uuid.UUID,
    body: SuggestRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(require_scope("search")),
):
    """Autocomplete and query suggestion endpoint."""
    if not auth.can_access_collection(collection_id):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "API key does not have access to this collection",
                }
            },
        )

    return await search_service.get_suggestions(db, collection_id, body)
