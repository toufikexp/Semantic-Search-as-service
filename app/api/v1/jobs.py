import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedKey, get_api_key
from app.core.database import get_db
from app.schemas.document import JobStatusResponse
from app.services import document_service

router = APIRouter()


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedKey = Depends(get_api_key),
):
    """Check the status of an asynchronous ingestion job."""
    job = await document_service.get_job_status(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Job not found"}},
        )
    return JobStatusResponse.model_validate(job)
