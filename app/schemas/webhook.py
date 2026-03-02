import uuid
from pydantic import BaseModel, Field


class WebhookCreate(BaseModel):
    source_platform: str = Field(..., max_length=50)
    event_types: list[str]
    field_mapping: dict = Field(default_factory=dict)
    secret: str | None = None


class WebhookResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    source_platform: str
    event_types: list[str]
    endpoint_url: str
    status: str


class CrawlRequest(BaseModel):
    sitemap_url: str | None = None
    max_pages: int = Field(default=500, ge=1, le=10000)
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    schedule: str | None = None


class CrawlResponse(BaseModel):
    job_id: uuid.UUID
    status: str = "started"
    pages_discovered: int = 0
