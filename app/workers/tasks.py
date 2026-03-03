import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import Document
from app.models.embedding import Embedding
from app.models.ingestion_job import IngestionJob
from app.services.chunking_service import chunk_text
from app.services.embedding_service import compute_embeddings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Synchronous engine for Celery workers
_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=5)
    return _sync_engine


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def process_ingestion_job(self, job_id: str):
    """Process all pending documents in an ingestion job: chunk, embed, index."""
    engine = _get_sync_engine()

    with Session(engine) as db:
        job = db.execute(
            select(IngestionJob).where(IngestionJob.id == job_id)
        ).scalar_one_or_none()

        if job is None:
            logger.error(f"Job {job_id} not found")
            return

        collection = db.execute(
            select(Collection).where(Collection.id == job.collection_id)
        ).scalar_one_or_none()

        if collection is None:
            logger.error(f"Collection {job.collection_id} not found for job {job_id}")
            return

        # Get all pending documents for this collection
        documents = (
            db.execute(
                select(Document).where(
                    Document.collection_id == job.collection_id,
                    Document.status == "pending",
                )
            )
            .scalars()
            .all()
        )

        errors = {}
        processed = 0

        for doc in documents:
            try:
                _process_single_document(db, doc, collection)
                processed += 1
            except Exception as e:
                logger.exception(f"Failed to process document {doc.external_id}")
                errors[doc.external_id] = str(e)
                doc.status = "failed"

        # Update job status
        job.processed_docs = job.processed_docs + processed
        job.failed_docs = len(errors)
        job.errors = errors
        job.status = "completed" if not errors else "completed_with_errors"

        # Update collection doc count
        total_docs = (
            db.execute(
                select(Document)
                .where(
                    Document.collection_id == collection.id,
                    Document.status == "indexed",
                )
            )
            .scalars()
            .all()
        )
        collection.doc_count = len(total_docs)

        db.commit()

    logger.info(
        f"Job {job_id} completed: {processed} processed, {len(errors)} errors"
    )


def _process_single_document(db: Session, doc: Document, collection: Collection):
    """Process a single document: chunk, embed, and index."""
    # Delete existing chunks and embeddings for upserts
    existing_chunks = (
        db.execute(
            select(Chunk).where(
                Chunk.document_id == doc.id,
                Chunk.collection_id == doc.collection_id,
            )
        )
        .scalars()
        .all()
    )
    for chunk in existing_chunks:
        db.delete(chunk)
    db.flush()

    # Stage 3: Chunking
    chunk_results = chunk_text(
        doc.content,
        strategy=collection.chunk_strategy,
        chunk_size=collection.chunk_size,
        chunk_overlap=collection.chunk_overlap,
    )

    if not chunk_results:
        doc.status = "indexed"
        doc.chunk_count = 0
        doc.indexed_at = datetime.now(timezone.utc)
        return

    # Create chunk records
    chunk_models = []
    chunk_texts = []
    for cr in chunk_results:
        text_for_embedding = cr.content
        if cr.heading_context:
            text_for_embedding = f"{cr.heading_context}: {cr.content}"
        chunk_texts.append(text_for_embedding)

        chunk_model = Chunk(
            document_id=doc.id,
            collection_id=doc.collection_id,
            chunk_index=cr.chunk_index,
            content=cr.content,
            token_count=cr.token_count,
            char_start=cr.char_start,
            char_end=cr.char_end,
            heading_context=cr.heading_context,
        )
        db.add(chunk_model)
        chunk_models.append(chunk_model)

    db.flush()

    # Stage 4: Embedding
    batch_size = settings.EMBEDDING_BATCH_SIZE
    all_vectors = []
    for i in range(0, len(chunk_texts), batch_size):
        batch = chunk_texts[i : i + batch_size]
        vectors = compute_embeddings(batch)
        all_vectors.extend(vectors)

    # Stage 5: Indexing
    for chunk_model, vector in zip(chunk_models, all_vectors):
        embedding = Embedding(
            chunk_id=chunk_model.id,
            collection_id=doc.collection_id,
            vector=vector,
            model_version=collection.embedding_model,
        )
        db.add(embedding)

    doc.status = "indexed"
    doc.chunk_count = len(chunk_models)
    doc.indexed_at = datetime.now(timezone.utc)
    db.flush()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def run_crawl(self, job_id: str, collection_id: str, crawl_config: dict):
    """Execute a website crawl and ingest discovered pages."""
    logger.info(f"Starting crawl job {job_id} for collection {collection_id}")

    import hashlib

    import httpx
    from bs4 import BeautifulSoup

    sitemap_url = crawl_config.get("sitemap_url")
    max_pages = crawl_config.get("max_pages", 500)
    include_patterns = crawl_config.get("include_patterns", [])
    exclude_patterns = crawl_config.get("exclude_patterns", [])

    urls = []

    if sitemap_url:
        try:
            response = httpx.get(sitemap_url, timeout=30, follow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml-xml")

            # Handle sitemap index files: if the sitemap contains <sitemap>
            # entries, fetch each child sitemap to collect page URLs.
            child_sitemaps = soup.find_all("sitemap")
            if child_sitemaps:
                for sm in child_sitemaps:
                    loc = sm.find("loc")
                    if not loc:
                        continue
                    try:
                        child_resp = httpx.get(
                            loc.text.strip(), timeout=30, follow_redirects=True
                        )
                        child_resp.raise_for_status()
                        child_soup = BeautifulSoup(child_resp.text, "lxml-xml")
                        for child_loc in child_soup.find_all("loc"):
                            page_url = child_loc.text.strip()
                            if _url_matches_patterns(
                                page_url, include_patterns, exclude_patterns
                            ):
                                urls.append(page_url)
                                if len(urls) >= max_pages:
                                    break
                    except Exception as e:
                        logger.warning(f"Failed to fetch child sitemap {loc.text}: {e}")
                    if len(urls) >= max_pages:
                        break
            else:
                for loc in soup.find_all("loc"):
                    url = loc.text.strip()
                    if _url_matches_patterns(url, include_patterns, exclude_patterns):
                        urls.append(url)
                        if len(urls) >= max_pages:
                            break
        except Exception as e:
            logger.error(f"Failed to parse sitemap {sitemap_url}: {e}")
            _update_job_status(job_id, "failed", errors={"sitemap": str(e)})
            return

    engine = _get_sync_engine()
    crawled = 0

    with Session(engine) as db:
        for url in urls:
            try:
                response = httpx.get(url, timeout=30, follow_redirects=True)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Remove scripts, styles, navigation
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                title = soup.title.string if soup.title else url
                content = soup.get_text(separator="\n", strip=True)

                if not content.strip():
                    continue

                content_hash = hashlib.sha256(content.encode()).hexdigest()
                external_id = hashlib.md5(url.encode()).hexdigest()

                doc = Document(
                    collection_id=collection_id,
                    external_id=external_id,
                    title=title,
                    content=content,
                    content_type="html",
                    url=url,
                    content_hash=content_hash,
                    status="pending",
                )
                db.merge(doc)
                crawled += 1

            except Exception as e:
                logger.warning(f"Failed to crawl {url}: {e}")

        # Update job with crawl totals
        job = db.execute(
            select(IngestionJob).where(IngestionJob.id == job_id)
        ).scalar_one_or_none()
        if job:
            job.total_docs = crawled
            job.status = "processing" if crawled > 0 else "completed"

        db.commit()

    logger.info(f"Crawl job {job_id}: crawled {crawled} pages from {len(urls)} URLs")

    # Trigger ingestion processing for crawled documents
    if crawled > 0:
        process_crawled_documents.delay(job_id, collection_id)
    else:
        _update_job_status(job_id, "completed")


@celery_app.task
def process_crawled_documents(job_id: str, collection_id: str):
    """Process pending documents from a crawl."""
    engine = _get_sync_engine()

    with Session(engine) as db:
        collection = db.execute(
            select(Collection).where(Collection.id == collection_id)
        ).scalar_one_or_none()

        if not collection:
            return

        job = db.execute(
            select(IngestionJob).where(IngestionJob.id == job_id)
        ).scalar_one_or_none()

        documents = (
            db.execute(
                select(Document).where(
                    Document.collection_id == collection_id,
                    Document.status == "pending",
                )
            )
            .scalars()
            .all()
        )

        errors = {}
        processed = 0

        for doc in documents:
            try:
                _process_single_document(db, doc, collection)
                processed += 1
            except Exception as e:
                logger.exception(f"Failed to process crawled doc {doc.external_id}")
                doc.status = "failed"
                errors[doc.external_id] = str(e)

        if job:
            job.processed_docs = processed
            job.failed_docs = len(errors)
            job.errors = errors
            job.status = "completed" if not errors else "completed_with_errors"

        collection.doc_count = (
            db.execute(
                select(Document).where(
                    Document.collection_id == collection_id,
                    Document.status == "indexed",
                )
            )
            .scalars()
            .all()
        ).__len__()

        db.commit()

    logger.info(
        f"Crawl ingestion job {job_id}: {processed} processed, {len(errors)} errors"
    )


def _update_job_status(job_id: str, status: str, errors: dict | None = None):
    """Helper to update an IngestionJob status from any task."""
    engine = _get_sync_engine()
    with Session(engine) as db:
        job = db.execute(
            select(IngestionJob).where(IngestionJob.id == job_id)
        ).scalar_one_or_none()
        if job:
            job.status = status
            if errors:
                job.errors = errors
            db.commit()


@celery_app.task
def compute_query_embedding(query: str) -> list[float]:
    """Compute embedding for a single search query (runs on embedding-worker)."""
    vectors = compute_embeddings([query])
    return vectors[0]


@celery_app.task
def cleanup_search_logs():
    """Remove search logs older than 90 days."""
    engine = _get_sync_engine()
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    with Session(engine) as db:
        from app.models.search_log import SearchLog

        db.execute(
            SearchLog.__table__.delete().where(SearchLog.created_at < cutoff)
        )
        db.commit()

    logger.info("Cleaned up old search logs")


def _url_matches_patterns(
    url: str, include: list[str], exclude: list[str]
) -> bool:
    """Check if a URL matches include/exclude glob patterns."""
    import fnmatch

    if exclude:
        for pattern in exclude:
            if fnmatch.fnmatch(url, f"*{pattern}"):
                return False

    if include:
        for pattern in include:
            if fnmatch.fnmatch(url, f"*{pattern}"):
                return True
        return False

    return True
