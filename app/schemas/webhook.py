import uuid
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


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
    sitemap_url: str = Field(
        ...,
        description=(
            "URL to a sitemap.xml file, or a base website URL. "
            "If a base URL is provided (e.g. https://example.com), "
            "/sitemap.xml is appended automatically. If the sitemap "
            "yields no URLs (e.g. broken child sitemaps), the crawler "
            "falls back to link-based discovery from the base domain."
        ),
    )
    max_pages: int = Field(default=500, ge=1, le=10000)
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    schedule: str | None = None

    @model_validator(mode="after")
    def ensure_sitemap_url(self) -> "CrawlRequest":
        """Auto-append /sitemap.xml if the URL doesn't point to an XML file."""
        parsed = urlparse(self.sitemap_url)
        if not parsed.scheme:
            self.sitemap_url = f"https://{self.sitemap_url}"
            parsed = urlparse(self.sitemap_url)
        path = parsed.path.rstrip("/")
        if not path.endswith(".xml"):
            self.sitemap_url = self.sitemap_url.rstrip("/") + "/sitemap.xml"
        return self


class CrawlResponse(BaseModel):
    job_id: uuid.UUID
    status: str = "started"
    pages_discovered: int = 0
