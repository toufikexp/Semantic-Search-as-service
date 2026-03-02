import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedKey, get_api_key, require_scope
from app.core.database import get_db
from app.schemas.document import (
    DocumentIngestRequest,
    DocumentIngestResponse,
    DocumentResponse,
)
from app.services import document_service

router = APIRouter()


@router.post("", response_model=DocumentIngestResponse, status_code=202)
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


@router.get("/{external_id}", response_model=DocumentResponse)
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


@router.delete("/{external_id}", status_code=204)
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

    deleted = await document_service.delete_document(db, collection_id, external_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Document not found"}},
        )
