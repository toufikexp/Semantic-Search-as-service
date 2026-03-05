# CLAUDE.md — Semantic Search as a Service

This file gives AI assistants a concise, accurate map of the codebase so they can make correct changes without re-reading every file.

---

## Project Overview

A production-ready, self-hosted semantic search platform. Clients ingest documents via a REST API; the platform chunks them, generates vector embeddings asynchronously, and supports semantic (vector), keyword (full-text), or hybrid search queries.

**Tech stack:**

| Layer | Technology |
|-------|-----------|
| API framework | FastAPI (Python 3.11+) |
| Database | PostgreSQL 16 + pgvector |
| Cache / task queue | Redis 7 + Celery 5 |
| Embeddings | sentence-transformers (BGE-M3, 1024-dim) |
| ORM / migrations | SQLAlchemy 2 (async) + Alembic |
| Reverse proxy | Nginx |
| Monitoring | Prometheus + prometheus-fastapi-instrumentator |
| Containerization | Docker Compose |

---

## Repository Layout

```
Semantic-Search-as-service/
├── app/
│   ├── main.py              # Search API (FastAPI app) — collections, search, suggest
│   ├── ingest.py            # Ingestion API (separate FastAPI app) — documents, jobs, webhooks/crawl
│   ├── api/v1/
│   │   ├── router.py        # Mounts all sub-routers for main.py
│   │   ├── collections.py   # CRUD for collections (master scope)
│   │   ├── documents.py     # Ingest / delete documents (ingest scope)
│   │   ├── search.py        # Search + suggest endpoints (search scope)
│   │   ├── jobs.py          # GET /jobs/{id} status (any scope)
│   │   └── webhooks.py      # Webhook registration + crawl trigger (master scope)
│   ├── core/
│   │   ├── config.py        # Pydantic-settings Settings singleton (`settings`)
│   │   ├── database.py      # Async SQLAlchemy engine + `get_db` dependency
│   │   ├── redis.py         # Async Redis client + `get_redis` dependency
│   │   ├── auth.py          # `get_api_key` dependency, `AuthenticatedKey`, `require_scope`
│   │   ├── security.py      # `hash_api_key` (SHA-256 hex)
│   │   └── rate_limit.py    # Sliding-window rate limiter (Redis ZSET, 60 s window)
│   ├── models/              # SQLAlchemy ORM models (one file per table)
│   │   ├── organization.py
│   │   ├── api_key.py
│   │   ├── collection.py
│   │   ├── document.py
│   │   ├── chunk.py
│   │   ├── embedding.py
│   │   ├── ingestion_job.py
│   │   └── search_log.py
│   ├── schemas/             # Pydantic v2 request/response schemas
│   │   ├── collection.py
│   │   ├── document.py
│   │   ├── search.py        # SearchRequest, SearchResponse, SuggestRequest/Response, FacetValue
│   │   ├── error.py
│   │   └── webhook.py
│   ├── services/
│   │   ├── search_service.py       # execute_search, _vector_search, _keyword_search, _merge_results, get_suggestions
│   │   ├── chunking_service.py     # chunk_text (adaptive / fixed / sentence / paragraph strategies)
│   │   ├── embedding_service.py    # compute_embeddings (sync, for workers), get_query_embedding (async, delegates to worker)
│   │   ├── collection_service.py   # Collection CRUD helpers
│   │   └── document_service.py     # Document ingest helpers
│   └── workers/
│       ├── celery_app.py           # Celery app configuration
│       └── tasks.py                # process_ingestion_job, run_crawl, process_crawled_documents,
│                                   # compute_query_embedding, cleanup_search_logs
├── docker/
│   ├── Dockerfile.api      # Used by search-api, ingestion-api, scheduler
│   ├── Dockerfile.gpu      # Embedding worker — bakes sentence-transformers model at build time
│   └── Dockerfile.crawler  # Crawler worker
├── migrations/
│   ├── env.py
│   └── versions/001_initial_schema.py   # Full schema: tables, GIN/HNSW indexes, extensions
├── nginx/conf.d/default.conf            # Routes /api/v1 to search-api or ingestion-api
├── tests/
│   ├── conftest.py                      # `client` fixture (ASGI transport over main.py app)
│   ├── api/test_health.py
│   └── services/test_chunking.py, test_security.py
├── scripts/reprocess_pending.py         # One-off: re-queue stuck pending documents
├── .env.example                         # All supported environment variables with defaults
├── docker-compose.yml                   # Full stack (see Services table below)
├── requirements.txt                     # Pinned dependencies
├── pyproject.toml                       # Build config, pytest settings, ruff config
└── alembic.ini
```

---

## Services (Docker Compose)

| Service | Internal port | Runs | Memory limit |
|---------|--------------|------|-------------|
| `postgres` | 5432 | PostgreSQL 16 + pgvector | 16 GB |
| `redis` | 6379 | Redis 7 (LRU, 4 GB max) | — |
| `search-api` (×2 replicas) | 8000 | `uvicorn app.main:app` | 1 GB each |
| `ingestion-api` | 8001 | `uvicorn app.ingest:app` | 1 GB |
| `embedding-worker` | — | Celery worker (loads ML model) | 4 GB |
| `crawler-worker` | — | Celery worker (httpx + BS4) | 2 GB |
| `scheduler` | — | `celery beat` | 512 MB |
| `nginx` | **80** (public) | Reverse proxy / gateway | — |

The **search-api does not load the embedding model**. Query embeddings are computed by the `embedding-worker` via a Celery task (`compute_query_embedding`) and cached in Redis (default 1-hour TTL, key `emb:query:<sha256>`).

---

## Authentication & Authorization

All API endpoints require `Authorization: Bearer <api_key>`. Keys are stored hashed (SHA-256) in the `api_keys` table.

Three scopes exist; `master` passes all scope checks:

| Scope | Access |
|-------|--------|
| `master` | Everything (create/delete collections, ingest, search, crawl) |
| `ingest` | Ingest and delete documents within the bound collection |
| `search` | Search and suggest within the bound collection |

Auth flow: `get_api_key` dependency → hash raw key → lookup `api_keys` → return `AuthenticatedKey`. Use `require_scope("ingest")` / `require_scope("search")` FastAPI dependency factories for per-route enforcement.

---

## API Endpoints (all prefixed `/api/v1`)

### Collections
| Method | Path | Scope |
|--------|------|-------|
| POST | `/collections` | master |
| GET | `/collections` | any |
| GET | `/collections/{id}` | any |
| PATCH | `/collections/{id}` | master |
| DELETE | `/collections/{id}` | master |

### Documents (Ingestion API)
| Method | Path | Scope |
|--------|------|-------|
| POST | `/collections/{id}/documents` | ingest |
| GET | `/collections/{id}/documents/{ext_id}` | any |
| DELETE | `/collections/{id}/documents/{ext_id}` | ingest |

### Search (Search API)
| Method | Path | Scope |
|--------|------|-------|
| POST | `/collections/{id}/search` | search |
| POST | `/collections/{id}/suggest` | search |

### Jobs & Webhooks
| Method | Path | Scope |
|--------|------|-------|
| GET | `/jobs/{job_id}` | any |
| POST | `/collections/{id}/webhooks` | master |
| POST | `/collections/{id}/crawl` | master |

Health checks: `GET /health` on both apps.

---

## Database Schema (8 tables)

All primary keys are UUID. Timestamps are `DateTime(timezone=True)`.

| Table | Key columns | Notes |
|-------|-------------|-------|
| `organizations` | `id`, `name`, `plan_tier` | Multi-tenant root |
| `api_keys` | `id`, `org_id`, `collection_id`, `key_hash`, `scope`, `rate_limit`, `is_active` | Partial index on `key_hash WHERE is_active` |
| `collections` | `id`, `org_id`, `name`, `embedding_model`, `chunk_strategy`, `chunk_size`, `chunk_overlap` | Unique constraint on `(org_id, name)` |
| `documents` | `id`, `collection_id`, `external_id`, `content`, `metadata` (JSONB), `status` | Unique on `(collection_id, external_id)`; GIN FTS + GIN metadata indexes |
| `chunks` | `id`, `document_id`, `collection_id`, `chunk_index`, `content`, `heading_context` | |
| `embeddings` | `id`, `chunk_id`, `collection_id`, `vector vector(1024)` | HNSW index (cosine, m=16, ef=200) |
| `ingestion_jobs` | `id`, `collection_id`, `status`, `total_docs`, `processed_docs`, `failed_docs`, `errors` (JSONB) | Statuses: `processing`, `completed`, `completed_with_errors`, `failed` |
| `search_logs` | `id`, `collection_id`, `query`, `mode`, `latency_ms`, `results_count` | Pruned every 90 days by scheduler |

Alembic is also run at app startup (`Base.metadata.create_all`) as a safety net. The migration file is `migrations/versions/001_initial_schema.py`.

---

## Document Processing Pipeline

```
POST /documents
  → document rows created with status="pending"
  → IngestionJob created
  → process_ingestion_job.delay(job_id)          [Celery: embedding-worker]
       ├── chunk_text(content, strategy, size, overlap)
       ├── compute_embeddings(chunk_texts)         [sentence-transformers]
       └── INSERT chunks + embeddings; doc.status = "indexed"
```

For crawls:
```
POST /crawl
  → run_crawl.delay(job_id, collection_id, config)  [Celery: crawler-worker]
       ├── fetch sitemap XML → collect URLs
       ├── httpx.get each URL → BeautifulSoup extract text
       ├── INSERT Document rows (status="pending")
       └── process_crawled_documents.delay(job_id, collection_id)
                → same chunk/embed/index loop as above
```

---

## Search Modes

| Mode | Mechanism |
|------|-----------|
| `semantic` | pgvector cosine ANN (`<=>` operator, HNSW index) |
| `keyword` | PostgreSQL `tsvector`/`tsquery` full-text search |
| `hybrid` | Both + score-weighted Reciprocal Rank Fusion (vector weight 0.7, keyword weight 0.3, k=60) |

The `SearchRequest` schema supports: `query`, `mode`, `limit`, `offset`, `filters`, `facets`, `min_score`, `highlight`.

---

## Chunking Strategies

Configured per-collection (`chunk_strategy` field):

| Strategy | Description |
|----------|-------------|
| `adaptive` (default) | Splits on markdown/HTML headings; sub-splits long sections by paragraph |
| `fixed` | Sliding window by character count (~4 chars/token), with overlap |
| `sentence` | Splits on sentence boundaries (`[.!?]`) |
| `paragraph` | Splits on blank-line paragraph breaks |

Token estimation: `len(text) // 4` (rough approximation, no tokenizer dependency).

---

## Embedding Models

Configured via `DEFAULT_EMBEDDING_MODEL` env var. Supported aliases in `embedding_service.py`:

| Alias | HuggingFace model |
|-------|------------------|
| `bge-m3` (default) | `BAAI/bge-m3` (1024-dim) |
| `multilingual-e5-large` | `intfloat/multilingual-e5-large` |
| `nomic-embed-text-v1.5` | `nomic-ai/nomic-embed-text-v1.5` |

The model is lazy-loaded on first use and cached in `_model`. `compute_embeddings` is synchronous (for Celery workers). `get_query_embedding` is async and routes through Celery + Redis cache.

---

## Configuration (Environment Variables)

All settings live in `app/core/config.py` as a `pydantic_settings.BaseSettings` class, loaded from `.env`. Copy `.env.example` to `.env` to start.

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:changeme@localhost:5432/semantic_search` | Async (API) |
| `DATABASE_URL_SYNC` | `postgresql://postgres:changeme@localhost:5432/semantic_search` | Sync (Celery workers) |
| `DB_PASSWORD` | `changeme` | Used by docker-compose |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `SECRET_KEY` | `your-secret-key-change-in-production` | Change in prod |
| `DEBUG` | `false` | Enables DEBUG logging |
| `API_V1_PREFIX` | `/api/v1` | |
| `DEFAULT_EMBEDDING_MODEL` | `bge-m3` | |
| `EMBEDDING_BATCH_SIZE` | `32` | |
| `EMBEDDING_DEVICE` | `cpu` | `cpu` or `cuda` |
| `EMBEDDING_DIM` | `1024` | Must match model output |
| `EMBEDDING_CACHE_TTL` | `3600` | Redis cache TTL for query embeddings (seconds) |
| `EMBEDDING_QUERY_TIMEOUT` | `10` | Celery result timeout (seconds) |
| `RATE_LIMIT_ENABLED` | `true` | |
| `MAX_CRAWL_PAGES` | `500` | |
| `CRAWL_DELAY_SECONDS` | `1.0` | |

---

## Development Workflows

### Local setup (without Docker)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Requires running Postgres+pgvector and Redis locally; update .env URLs
alembic upgrade head
uvicorn app.main:app --reload        # Search API on :8000
uvicorn app.ingest:app --port 8001   # Ingestion API on :8001
celery -A app.workers.celery_app worker --loglevel=info
```

### Docker (recommended)

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec search-api alembic upgrade head
curl http://localhost/health
```

### Running Tests

```bash
# Inside Docker:
docker compose exec search-api pytest tests/ -v

# Locally:
pytest tests/ -v
pytest tests/ -v --cov=app
```

Tests use `pytest-asyncio` in `auto` mode (set in `pyproject.toml`). The `client` fixture in `tests/conftest.py` wraps `app.main:app` via `httpx.AsyncClient(ASGITransport(...))`.

### Linting

```bash
ruff check app/ tests/
ruff format app/ tests/
```

Line length: **100**. Target: **py311**.

### Database migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "describe change"

# Apply
alembic upgrade head

# Rollback one
alembic downgrade -1
```

---

## Key Conventions

1. **Two separate FastAPI apps:** `app.main:app` (search-api, port 8000) and `app.ingest:app` (ingestion-api, port 8001). Do not merge them — they are independently scaled.

2. **Async API, sync workers:** API routes use `AsyncSession` from `app.core.database.get_db`. Celery tasks use a synchronous SQLAlchemy engine (`DATABASE_URL_SYNC`) via `_get_sync_engine()` in `tasks.py`.

3. **No model loading in the API process:** The search-api never imports `sentence-transformers`. All embedding computation (including query-time) is delegated to the `embedding-worker` Celery task and cached in Redis.

4. **Error response format:** All errors follow:
   ```json
   {"error": {"code": "ERROR_CODE", "message": "...", "request_id": "<uuid>"}}
   ```
   Use the existing exception handlers in `main.py`/`ingest.py` rather than inventing new formats.

5. **API keys are hashed, never stored plaintext.** The raw key is only shown once at creation. Auth lookup: `hash_api_key(raw) → api_keys.key_hash`.

6. **Rate limiting:** Sliding-window via Redis sorted sets, per `api_key.id`. Limit is stored per key in `api_keys.rate_limit` (requests/minute). Headers `X-RateLimit-Limit/Remaining/Reset` are always set.

7. **Document status lifecycle:** `pending` → `indexed` (or `failed`). Only `indexed` documents appear in search results.

8. **Upserts:** Posting a document with an existing `external_id` replaces it. Workers delete existing chunks/embeddings before re-processing.

9. **Facets:** Computed from JSONB `documents.metadata`. Facet fields must be valid keys of that JSONB column.

10. **Highlight generation:** Semantic search uses a Python snippet extractor (`_generate_highlight`). Keyword search uses PostgreSQL `ts_headline`.

11. **Search logging:** Every search (including failed/partial ones) is logged to `search_logs` inside a `finally` block in `execute_search`. This is intentional — don't remove it.

12. **Scheduled tasks:** `cleanup_search_logs` (deletes rows older than 90 days) runs via Celery beat (`scheduler` service).

---

## Adding a New Feature — Checklist

- [ ] Add/update ORM model in `app/models/` and register it in `app/models/__init__.py`
- [ ] Create an Alembic migration: `alembic revision --autogenerate -m "..."`
- [ ] Add Pydantic schemas in `app/schemas/`
- [ ] Implement business logic in `app/services/`
- [ ] Add route handler in `app/api/v1/` and mount it in `router.py` (and `ingest.py` if ingestion-only)
- [ ] Apply the correct scope dependency: `Depends(require_scope("master"|"ingest"|"search"))`
- [ ] Add tests in `tests/`

---

## Common Pitfalls

- **Don't import `sentence_transformers` or call `compute_embeddings` from the API process.** Use `get_query_embedding()` which dispatches to the worker.
- **Don't use `DATABASE_URL` (asyncpg) in Celery tasks.** Use `DATABASE_URL_SYNC` (psycopg2).
- **Vector dimension must match model output.** `EMBEDDING_DIM=1024` is correct for BGE-M3. Changing the model requires a new migration to alter `embeddings.vector`.
- **`collection_id` is a UUID.** Pass it as `str(collection_id)` in raw SQL params.
- **`models/__init__.py` must import all model classes** so `Base.metadata` sees them at startup. Check this when adding a new table.
