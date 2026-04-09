import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedKey, require_scope
from app.core.database import get_db
from app.schemas.webhook import (
    CrawlRequest,
    CrawlResponse,
    WebhookCreate,
    WebhookResponse,
)
from app.services import collection_service

router = APIRouter()


@router.post("/webhooks", response_model=WebhookResponse, status_code=201)
async def register_webhook(
    collection_id: uuid.UUID,
    body: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(require_scope("master")),
):
    """Register a webhook configuration for automated content ingestion."""
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

    webhook_id = uuid.uuid4()
    endpoint_url = f"/api/v1/collections/{collection_id}/webhooks/{webhook_id}/receive"

    return WebhookResponse(
        id=webhook_id,
        collection_id=collection_id,
        source_platform=body.source_platform,
        event_types=body.event_types,
        endpoint_url=endpoint_url,
        status="active",
    )


@router.post("/crawl", response_model=CrawlResponse, status_code=202)
async def trigger_crawl(
    collection_id: uuid.UUID,
    body: CrawlRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(require_scope("master")),
):
    """Trigger an on-demand crawl of the target website."""
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

    from app.models.ingestion_job import IngestionJob
    from app.workers.tasks import run_crawl

    job = IngestionJob(
        collection_id=collection_id,
        status="crawling",
        total_docs=0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    run_crawl.delay(
        str(job.id),
        str(collection_id),
        body.model_dump(),
    )

    return CrawlResponse(
        job_id=job.id,
        status="started",
        pages_discovered=0,
    )
