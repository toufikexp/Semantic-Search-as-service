import uuid
from datetime import datetime

from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    embedding_model: str = "bge-m3"
    language: str = "auto"
    chunk_strategy: str = "adaptive"
    chunk_size: int = 512
    chunk_overlap: int = 50
    metadata_schema: dict = Field(default_factory=dict)
    callback_url: str | None = None
    callback_secret: str | None = None

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("callback_url must be a valid HTTP or HTTPS URL")
        return v


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    metadata_schema: dict | None = None
    embedding_model: str | None = None
    chunk_strategy: str | None = None
    language: str | None = None
    callback_url: str | None = None
    callback_secret: str | None = None

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("callback_url must be a valid HTTP or HTTPS URL")
        return v


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
    callback_url: str | None = None
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
