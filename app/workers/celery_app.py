from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "semantic_search",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.process_ingestion_job": {"queue": "embeddings"},
        "app.workers.tasks.run_crawl": {"queue": "crawling"},
    },
    beat_schedule={
        "cleanup-old-search-logs": {
            "task": "app.workers.tasks.cleanup_search_logs",
            "schedule": 86400.0,  # daily
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])
