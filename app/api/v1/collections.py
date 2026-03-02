import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedKey, get_api_key, require_scope
from app.core.database import get_db
from app.schemas.collection import (
    CollectionCreate,
    CollectionCreateResponse,
    CollectionListResponse,
    CollectionResponse,
    CollectionUpdate,
)
from app.services import collection_service

router = APIRouter()


@router.post("", response_model=CollectionCreateResponse, status_code=201)
async def create_collection(
    body: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(require_scope("master")),
):
    """Create a new collection namespace."""
    collection, raw_keys = await collection_service.create_collection(
        db, auth.org_id, body
    )
    return CollectionCreateResponse(
        id=collection.id,
        name=collection.name,
        status=collection.status,
        api_keys={"ingest": raw_keys["ingest"], "search": raw_keys["search"]},
        created_at=collection.created_at,
    )


@router.get("", response_model=CollectionListResponse)
async def list_collections(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(get_api_key),
):
    """List all collections for the authenticated organization."""
    collections, total = await collection_service.list_collections(
        db, auth.org_id, limit, offset
    )
    return CollectionListResponse(
        collections=[CollectionResponse.model_validate(c) for c in collections],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(get_api_key),
):
    """Get detailed information about a single collection."""
    collection = await collection_service.get_collection(db, collection_id)
    if collection is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Collection not found"}},
        )
    return CollectionResponse.model_validate(collection)


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(require_scope("master")),
):
    """Update mutable collection properties."""
    collection = await collection_service.update_collection(db, collection_id, body)
    if collection is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Collection not found"}},
        )
    return CollectionResponse.model_validate(collection)


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(require_scope("master")),
):
    """Permanently delete a collection and all associated data."""
    deleted = await collection_service.delete_collection(db, collection_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Collection not found"}},
        )
