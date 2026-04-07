import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key
from app.models.api_key import ApiKey
from app.models.collection import Collection
from app.schemas.collection import CollectionCreate, CollectionUpdate


async def create_collection(
    db: AsyncSession, org_id: uuid.UUID, data: CollectionCreate
) -> tuple[Collection, dict[str, str]]:
    """Create a new collection and generate ingest/search API keys."""
    collection = Collection(
        org_id=org_id,
        name=data.name,
        description=data.description,
        embedding_model=data.embedding_model,
        language=data.language,
        chunk_strategy=data.chunk_strategy,
        chunk_size=data.chunk_size,
        chunk_overlap=data.chunk_overlap,
        metadata_schema=data.metadata_schema,
        callback_url=data.callback_url,
        callback_secret=data.callback_secret,
    )
    db.add(collection)
    await db.flush()

    raw_keys = {}
    for scope in ("ingest", "search"):
        raw_key, key_hash = generate_api_key(scope)
        api_key = ApiKey(
            org_id=org_id,
            collection_id=collection.id,
            key_hash=key_hash,
            key_prefix=raw_key[:12],
            scope=scope,
            rate_limit=600 if scope == "search" else 100,
        )
        db.add(api_key)
        raw_keys[scope] = raw_key

    await db.commit()
    await db.refresh(collection)
    return collection, raw_keys


async def list_collections(
    db: AsyncSession, org_id: uuid.UUID, limit: int = 20, offset: int = 0
) -> tuple[list[Collection], int]:
    """List all collections for an organization."""
    count_result = await db.execute(
        select(func.count()).select_from(Collection).where(Collection.org_id == org_id)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Collection)
        .where(Collection.org_id == org_id)
        .order_by(Collection.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    collections = list(result.scalars().all())
    return collections, total


async def get_collection(
    db: AsyncSession, collection_id: uuid.UUID
) -> Collection | None:
    """Get a single collection by ID."""
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    return result.scalar_one_or_none()


async def update_collection(
    db: AsyncSession, collection_id: uuid.UUID, data: CollectionUpdate
) -> Collection | None:
    """Update mutable collection properties."""
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    if collection is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(collection, field, value)

    await db.commit()
    await db.refresh(collection)
    return collection


async def delete_collection(db: AsyncSession, collection_id: uuid.UUID) -> bool:
    """Delete a collection and all associated data."""
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    if collection is None:
        return False

    await db.delete(collection)
    await db.commit()
    return True
