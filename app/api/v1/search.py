import logging
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
from app.services import collection_service, search_service

logger = logging.getLogger(__name__)

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

    collection = await collection_service.ensure_collection_exists(db, collection_id)

    # Generate query embedding for semantic/hybrid search
    query_vector = None
    if body.mode in ("semantic", "hybrid"):
        try:
            from app.services.embedding_service import get_query_embedding

            query_vector = await get_query_embedding(body.query)
        except Exception:
            logger.exception("Failed to generate query embedding")
            if body.mode == "semantic":
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": {
                            "code": "EMBEDDING_UNAVAILABLE",
                            "message": "Embedding service is currently unavailable. "
                            "Try mode='keyword' or mode='hybrid' as a fallback.",
                        }
                    },
                )
            # For hybrid mode, fall back to keyword-only search
            logger.warning(
                "Falling back to keyword-only search for hybrid query"
            )

    # Collection language for keyword/hybrid text search config
    language = collection.language

    return await search_service.execute_search(
        db, collection_id, body, query_vector, language=language
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

    await collection_service.ensure_collection_exists(db, collection_id)

    return await search_service.get_suggestions(db, collection_id, body)
