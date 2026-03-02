import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentInput(BaseModel):
    external_id: str = Field(..., max_length=255)
    content: str
    content_type: str = "text"
    title: str | None = None
    url: str | None = None
    metadata: dict = Field(default_factory=dict)


class DocumentIngestRequest(BaseModel):
    documents: list[DocumentInput] = Field(..., min_length=1)
    upsert: bool = True


class DocumentIngestResponse(BaseModel):
    job_id: uuid.UUID
    documents_queued: int
    status: str = "processing"


class DocumentResponse(BaseModel):
    id: uuid.UUID
    external_id: str
    collection_id: uuid.UUID
    title: str | None
    content_type: str
    url: str | None
    metadata: dict
    content_hash: str | None
    chunk_count: int
    status: str
    indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobStatusResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    status: str
    total_docs: int
    processed_docs: int
    failed_docs: int
    errors: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
