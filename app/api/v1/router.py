from fastapi import APIRouter

from app.api.v1 import collections, documents, search, webhooks, jobs

api_router = APIRouter()

api_router.include_router(
    collections.router, prefix="/collections", tags=["Collections"]
)
api_router.include_router(
    documents.router, prefix="/collections/{collection_id}/documents", tags=["Documents"]
)
api_router.include_router(
    search.router, prefix="/collections/{collection_id}", tags=["Search"]
)
api_router.include_router(
    webhooks.router, prefix="/collections/{collection_id}", tags=["Webhooks & Crawl"]
)
api_router.include_router(
    jobs.router, prefix="/jobs", tags=["Jobs"]
)
