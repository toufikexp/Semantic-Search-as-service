import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    embedding_model: str = "bge-m3"
    language: str = "auto"
    chunk_strategy: str = "adaptive"
    chunk_size: int = 512
    chunk_overlap: int = 50
    metadata_schema: dict = Field(default_factory=dict)


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    metadata_schema: dict | None = None
    embedding_model: str | None = None
    chunk_strategy: str | None = None


class CollectionApiKeys(BaseModel):
    ingest: str
    search: str


class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    status: str
    embedding_model: str
    chunk_strategy: str
    language: str
    doc_count: int
    metadata_schema: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    api_keys: CollectionApiKeys
    created_at: datetime


class CollectionListResponse(BaseModel):
    collections: list[CollectionResponse]
    total: int
    limit: int
    offset: int
