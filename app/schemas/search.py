import uuid
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: str = "hybrid"
    filters: dict = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    highlight: bool = True
    facets: list[str] = Field(default_factory=list)
    rerank: bool = False
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchResult(BaseModel):
    doc_id: uuid.UUID
    external_id: str
    score: float
    title: str | None
    url: str | None
    highlights: list[str]
    metadata: dict


class FacetValue(BaseModel):
    value: str
    count: int


class SearchResponse(BaseModel):
    results: list[SearchResult]
    facets: dict[str, list[FacetValue]]
    total: int
    query_id: uuid.UUID
    took_ms: int


class SuggestRequest(BaseModel):
    prefix: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class SuggestResponse(BaseModel):
    suggestions: list[str]
