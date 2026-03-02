import logging

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded model cache
_model = None


def _get_model():
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        model_name_map = {
            "bge-m3": "BAAI/bge-m3",
            "multilingual-e5-large": "intfloat/multilingual-e5-large",
            "nomic-embed-text-v1.5": "nomic-ai/nomic-embed-text-v1.5",
        }
        model_name = model_name_map.get(
            settings.DEFAULT_EMBEDDING_MODEL, settings.DEFAULT_EMBEDDING_MODEL
        )
        logger.info(f"Loading embedding model: {model_name}")
        _model = SentenceTransformer(model_name, device=settings.EMBEDDING_DEVICE)
    return _model


def compute_embeddings(texts: list[str]) -> list[list[float]]:
    """Compute embeddings for a batch of texts synchronously (for Celery workers)."""
    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings.tolist()


async def get_query_embedding(query: str) -> list[float]:
    """Get embedding for a search query.

    Delegates to the embedding-worker via Celery so the search-api never
    loads the model.  Results are cached in Redis to avoid repeated calls.
    """
    import asyncio
    import hashlib
    import json

    import redis

    cache_key = f"emb:query:{hashlib.sha256(query.encode()).hexdigest()}"
    r = redis.Redis.from_url(settings.REDIS_URL)

    # Check cache first
    cached = r.get(cache_key)
    if cached is not None:
        return json.loads(cached)

    # Dispatch to embedding-worker and wait for the result
    from app.workers.tasks import compute_query_embedding

    loop = asyncio.get_event_loop()
    async_result = compute_query_embedding.delay(query)
    vector = await loop.run_in_executor(
        None, async_result.get, settings.EMBEDDING_QUERY_TIMEOUT
    )

    # Cache for future queries
    r.setex(cache_key, settings.EMBEDDING_CACHE_TTL, json.dumps(vector))

    return vector
