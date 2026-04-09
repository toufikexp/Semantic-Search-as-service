"""Separate ingestion API application for independent scaling."""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
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
    description=(
        "Document ingestion, crawling and webhook endpoints. All routes "
        "require an `Authorization: Bearer <api_key>` header. Document "
        "ingestion is asynchronous: the API returns a job_id immediately "
        "and the platform delivers a signed completion webhook to the "
        "collection's callback_url when processing finishes."
    ),
    version="1.0.0",
)

Instrumentator().instrument(app).expose(app)

logger = logging.getLogger(__name__)


@app.on_event("startup")
async def on_startup():
    """Create database tables and enable pgvector if they don't exist yet."""
    from sqlalchemy import text as sa_text

    from app.core.database import Base, engine
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created")


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


def custom_openapi():
    """Inject a Bearer-token security scheme into the generated OpenAPI
    document so the Swagger UI 'Authorize' button works and SDK generators
    know every endpoint requires `Authorization: Bearer <api_key>`."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "description": (
                "Provide your API key as `Authorization: Bearer <api_key>`. "
                "Keys are scoped to `master`, `ingest`, or `search`."
            ),
        }
    }
    schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


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
