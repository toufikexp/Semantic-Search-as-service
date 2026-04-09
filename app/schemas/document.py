import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentInput(BaseModel):
    external_id: str = Field(
        ...,
        max_length=255,
        description=(
            "Client-provided unique identifier for this document within the "
            "collection. Re-posting the same external_id with upsert=true "
            "replaces the previous version."
        ),
    )
    content: str = Field(
        ...,
        description="Raw text content of the document. Will be chunked and embedded.",
    )
    content_type: str = Field(
        "text",
        description="Content format hint. One of: text, markdown, html.",
    )
    title: str | None = Field(None, description="Optional human-readable title.")
    url: str | None = Field(None, description="Optional source URL for the document.")
    metadata: dict = Field(
        default_factory=dict,
        description=(
            "Arbitrary JSON metadata. Keys declared in the collection's "
            "metadata_schema can be used as search filters and facets."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "external_id": "cv-2026-001",
                "title": "Sarah Benali - Senior Backend Engineer",
                "content_type": "text",
                "content": "Sarah Benali\nSenior Backend Engineer\n8 years Python...",
                "url": "https://hiring.example.com/cvs/cv-2026-001.pdf",
                "metadata": {
                    "category": "cv",
                    "candidate_id": "cand_7788",
                    "years_experience": 8,
                    "skills": ["python", "fastapi", "postgresql"],
                    "location": "Algiers",
                },
            }
        }
    }


class DocumentIngestRequest(BaseModel):
    documents: list[DocumentInput] = Field(..., min_length=1, max_length=1000)
    upsert: bool = Field(
        True,
        description=(
            "If true (default), re-ingesting a document with an existing "
            "external_id replaces its content, chunks and embeddings. If "
            "false, a duplicate external_id causes the document to be skipped."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "upsert": True,
                "documents": [
                    {
                        "external_id": "cv-2026-001",
                        "title": "Sarah Benali - Senior Backend Engineer",
                        "content_type": "text",
                        "content": "Sarah Benali\n8 years Python, FastAPI, PostgreSQL...",
                        "metadata": {
                            "category": "cv",
                            "candidate_id": "cand_7788",
                            "years_experience": 8,
                            "skills": ["python", "fastapi", "postgresql"],
                        },
                    }
                ],
            }
        }
    }


class DocumentIngestResponse(BaseModel):
    job_id: uuid.UUID = Field(
        ...,
        description=(
            "Ingestion job ID. Poll GET /jobs/{job_id} to check progress, "
            "or wait for the ingestion.completed webhook callback if the "
            "collection has a callback_url configured."
        ),
    )
    documents_queued: int = Field(
        ..., description="Number of documents accepted for async processing."
    )
    status: str = Field(
        "processing",
        description='Initial job status, always "processing" on accept.',
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "7a1f2e9b-4c8d-4a3b-8e1f-2d9c5a6b7f80",
                "documents_queued": 1,
                "status": "processing",
            }
        }
    }


class IngestionCallbackDocumentStatus(BaseModel):
    """Per-document entry inside an ingestion callback payload."""

    external_id: str = Field(..., description="Client-provided document id.")
    status: str = Field(..., description='"indexed" or "failed".')
    error: str | None = Field(
        None,
        description="Error message if status is 'failed'; absent otherwise.",
    )


class IngestionCallbackPayload(BaseModel):
    """Payload POSTed to a collection's callback_url when an ingestion job
    reaches a terminal state (completed, completed_with_errors, or failed).

    This is the schema of the webhook the platform SENDS. The CV intelligence
    layer must host an endpoint that accepts this shape. The webhook is
    signed with HMAC-SHA256 in the `X-Webhook-Signature` header if a
    callback_secret is configured on the collection.

    Delivery is best-effort: up to 3 attempts with a 10s timeout each.
    Failed deliveries are logged but do not affect the ingestion itself;
    the data is already persisted and searchable before the callback fires.
    """

    event: str = Field(
        ..., description='Always "ingestion.completed" for this event type.'
    )
    job_id: uuid.UUID = Field(
        ..., description="Ingestion job id, matches the value returned by the ingest API."
    )
    collection_id: uuid.UUID = Field(..., description="Target collection id.")
    status: str = Field(
        ...,
        description=(
            'Terminal job status. One of: "completed", '
            '"completed_with_errors", "failed".'
        ),
    )
    total_docs: int = Field(..., description="Total documents in the batch.")
    processed_docs: int = Field(
        ..., description="Documents successfully chunked, embedded and indexed."
    )
    failed_docs: int = Field(..., description="Documents that failed processing.")
    documents: list[IngestionCallbackDocumentStatus] = Field(
        ..., description="Per-document status list."
    )
    completed_at: datetime = Field(
        ..., description="UTC timestamp when the job reached its terminal state."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "event": "ingestion.completed",
                "job_id": "7a1f2e9b-4c8d-4a3b-8e1f-2d9c5a6b7f80",
                "collection_id": "dd8aa5b5-7b2a-4e1c-9f0d-1a2b3c4d5e6f",
                "status": "completed",
                "total_docs": 2,
                "processed_docs": 2,
                "failed_docs": 0,
                "documents": [
                    {"external_id": "cv-2026-001", "status": "indexed"},
                    {"external_id": "cv-2026-002", "status": "indexed"},
                ],
                "completed_at": "2026-04-09T12:11:33.158000+00:00",
            }
        }
    }


class IngestionCallbackAck(BaseModel):
    """Response the webhook receiver should return. Any 2xx is treated as
    success; non-2xx triggers up to 3 retries before giving up."""

    received: bool = True

    model_config = {"json_schema_extra": {"example": {"received": True}}}


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
