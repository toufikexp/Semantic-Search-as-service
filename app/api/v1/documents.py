import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedKey, get_api_key, require_scope
from app.core.database import get_db
from app.schemas.document import (
    DocumentIngestRequest,
    DocumentIngestResponse,
    DocumentResponse,
    IngestionCallbackAck,
    IngestionCallbackPayload,
)
from app.schemas.error import COMMON_ERROR_RESPONSES
from app.services import collection_service, document_service

router = APIRouter()

# OpenAPI 3.0 "callbacks" declaration for the ingestion.completed webhook.
# This tells clients generating SDKs from /openapi.json the exact shape of
# the webhook the platform will POST to their callback_url when processing
# finishes. The {$request.body#/callback_url} placeholder references the
# callback_url field set on the collection at creation time.
ingestion_callback_router = APIRouter()


@ingestion_callback_router.post(
    "{$request.body#/callback_url}",
    response_model=IngestionCallbackAck,
    summary="Ingestion completion webhook (platform → client)",
    description=(
        "Signed HMAC-SHA256 webhook delivered to the collection's "
        "callback_url when an ingestion job reaches a terminal state. "
        "The client is expected to return any 2xx to acknowledge; non-2xx "
        "triggers up to 3 retries with a 10s timeout each."
    ),
)
def ingestion_completed_callback(body: IngestionCallbackPayload) -> IngestionCallbackAck:
    """This function exists only to generate OpenAPI documentation for the
    outgoing webhook. It is never actually called."""
    ...  # pragma: no cover


@router.post(
    "",
    response_model=DocumentIngestResponse,
    status_code=202,
    responses=COMMON_ERROR_RESPONSES,
    callbacks=ingestion_callback_router.routes,
    summary="Ingest documents into a collection",
    description=(
        "Accepts a batch of documents, persists them with status='pending', "
        "creates an ingestion job and dispatches an async Celery task. "
        "Returns 202 immediately with the job id.\n\n"
        "The worker then chunks each document, computes BGE-M3 embeddings "
        "and indexes the chunks. When the job reaches a terminal state "
        "(completed / completed_with_errors / failed) the platform POSTs "
        "the signed webhook documented in the `callbacks` section to the "
        "collection's `callback_url` if one is configured.\n\n"
        "Required scope: `ingest` or `master`."
    ),
)
async def ingest_documents(
    collection_id: uuid.UUID,
    body: DocumentIngestRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(require_scope("ingest")),
):
    """Ingest one or more documents into a collection."""
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

    job = await document_service.ingest_documents(
        db, collection_id, body.documents, body.upsert
    )

    # Dispatch async processing task
    from app.workers.tasks import process_ingestion_job

    process_ingestion_job.delay(str(job.id))

    return DocumentIngestResponse(
        job_id=job.id,
        documents_queued=job.total_docs,
        status=job.status,
    )


@router.get(
    "/{external_id}",
    response_model=DocumentResponse,
    responses=COMMON_ERROR_RESPONSES,
    summary="Retrieve a document by external_id",
    description=(
        "Returns the document's metadata and current processing status. "
        "Use this to check whether a specific document is ready for search "
        "(`status=='indexed'`) or still pending."
    ),
)
async def get_document(
    collection_id: uuid.UUID,
    external_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(get_api_key),
):
    """Retrieve a single document by its external ID."""
    doc = await document_service.get_document(db, collection_id, external_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Document not found"}},
        )
    return DocumentResponse(
        id=doc.id,
        external_id=doc.external_id,
        collection_id=doc.collection_id,
        job_id=doc.job_id,
        title=doc.title,
        content_type=doc.content_type,
        url=doc.url,
        metadata=doc.metadata_,
        content_hash=doc.content_hash,
        chunk_count=doc.chunk_count,
        status=doc.status,
        indexed_at=doc.indexed_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.delete(
    "/{external_id}",
    status_code=204,
    responses=COMMON_ERROR_RESPONSES,
    summary="Delete a document and all its chunks and embeddings",
    description=(
        "Removes the document row plus cascade-deletes its chunks and "
        "embeddings. The operation is synchronous and idempotent.\n\n"
        "Required scope: `ingest` or `master`."
    ),
)
async def delete_document(
    collection_id: uuid.UUID,
    external_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(require_scope("ingest")),
):
    """Remove a document and all its associated chunks and embeddings."""
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

    deleted = await document_service.delete_document(db, collection_id, external_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Document not found"}},
        )
