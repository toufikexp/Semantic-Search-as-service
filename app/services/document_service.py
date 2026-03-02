import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.schemas.document import DocumentInput


async def ingest_documents(
    db: AsyncSession,
    collection_id: uuid.UUID,
    documents: list[DocumentInput],
    upsert: bool = True,
) -> IngestionJob:
    """Create documents and an ingestion job for async processing."""
    job = IngestionJob(
        collection_id=collection_id,
        total_docs=len(documents),
        status="processing",
    )
    db.add(job)

    for doc_input in documents:
        content_hash = hashlib.sha256(doc_input.content.encode()).hexdigest()

        if upsert:
            result = await db.execute(
                select(Document).where(
                    Document.collection_id == collection_id,
                    Document.external_id == doc_input.external_id,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                if existing.content_hash == content_hash:
                    # Content unchanged, skip re-embedding
                    job.processed_docs += 1
                    continue
                existing.content = doc_input.content
                existing.title = doc_input.title
                existing.url = doc_input.url
                existing.metadata_ = doc_input.metadata
                existing.content_hash = content_hash
                existing.content_type = doc_input.content_type
                existing.status = "pending"
                continue

        doc = Document(
            collection_id=collection_id,
            external_id=doc_input.external_id,
            content=doc_input.content,
            content_type=doc_input.content_type,
            title=doc_input.title,
            url=doc_input.url,
            metadata_=doc_input.metadata,
            content_hash=content_hash,
            status="pending",
        )
        db.add(doc)

    await db.commit()
    await db.refresh(job)
    return job


async def get_document(
    db: AsyncSession, collection_id: uuid.UUID, external_id: str
) -> Document | None:
    """Get a single document by external ID."""
    result = await db.execute(
        select(Document).where(
            Document.collection_id == collection_id,
            Document.external_id == external_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_document(
    db: AsyncSession, collection_id: uuid.UUID, external_id: str
) -> bool:
    """Delete a document and all associated chunks/embeddings."""
    result = await db.execute(
        select(Document).where(
            Document.collection_id == collection_id,
            Document.external_id == external_id,
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        return False

    await db.delete(doc)
    await db.commit()
    return True


async def get_job_status(
    db: AsyncSession, job_id: uuid.UUID
) -> IngestionJob | None:
    """Get the status of an ingestion job."""
    result = await db.execute(
        select(IngestionJob).where(IngestionJob.id == job_id)
    )
    return result.scalar_one_or_none()
