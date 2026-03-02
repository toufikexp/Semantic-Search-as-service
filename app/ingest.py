"""Separate ingestion API application for independent scaling."""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1 import documents, jobs, webhooks
from app.core.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(
    title="Semantic Search Ingestion API",
    description="Document ingestion and crawling endpoints",
    version="1.0.0",
)

Instrumentator().instrument(app).expose(app)

# Include only ingestion-related routes
app.include_router(
    documents.router,
    prefix=f"{settings.API_V1_PREFIX}/collections/{{collection_id}}/documents",
    tags=["Documents"],
)
app.include_router(
    jobs.router,
    prefix=f"{settings.API_V1_PREFIX}/jobs",
    tags=["Jobs"],
)
app.include_router(
    webhooks.router,
    prefix=f"{settings.API_V1_PREFIX}/collections/{{collection_id}}",
    tags=["Webhooks & Crawl"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "details": {"errors": exc.errors()},
                "request_id": str(uuid.uuid4()),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.getLogger(__name__).error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "request_id": str(uuid.uuid4()),
            }
        },
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ingestion", "version": "1.0.0"}
