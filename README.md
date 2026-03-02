# Semantic Search as a Service

A production-ready, self-hosted semantic search platform that adds powerful search capabilities to any web application. Ingest documents via API, automatically generate vector embeddings, and query using semantic, keyword, or hybrid search — all behind a simple REST API.

## Features

- **Hybrid Search** — Combine vector (semantic) and full-text (keyword) search with reciprocal rank fusion
- **Automatic Embeddings** — Documents are chunked and embedded asynchronously using BGE-M3 (or configurable models)
- **Multi-tenant** — Organizations, scoped API keys (master / ingest / search), and per-key rate limiting
- **Web Crawling** — Built-in crawler to ingest content directly from websites
- **Autocomplete** — Suggestion endpoint powered by document titles and popular past queries
- **Faceted Search** — Compute facet counts over document metadata fields
- **Async Pipeline** — Celery workers handle embedding generation (including search-time query embeddings) and crawling in the background
- **Observability** — Prometheus metrics, structured logging, and search analytics (query logs)
- **Dockerized** — Full stack orchestrated with Docker Compose (PostgreSQL + pgvector, Redis, Nginx, API, workers)
- **Offline / Air-Gapped** — The BGE-M3 embedding model is baked into the Docker image at build time; no internet access is needed at runtime

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI (Python 3.11+) |
| Database | PostgreSQL 16 + pgvector |
| Cache / Queue | Redis 7 + Celery |
| Embeddings | sentence-transformers (BGE-M3) |
| Reverse Proxy | Nginx |
| Monitoring | Prometheus + FastAPI Instrumentator |
| Containerization | Docker Compose |

## Architecture

```
┌─────────┐       ┌───────────────────────────────────────────────┐
│  Client  │──80──▶│  Nginx (reverse proxy + rate limiting)        │
└─────────┘       └──────┬───────────────────┬────────────────────┘
                         │                   │
                  ┌──────▼──────┐     ┌──────▼──────┐
                  │ Search API  │     │ Ingestion   │
                  │ (x2 replicas)│     │ API         │
                  └──────┬──────┘     └──────┬──────┘
                         │                   │
              ┌──────────▼───────────────────▼──────────┐
              │         PostgreSQL 16 + pgvector         │
              └──────────▲──────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │  Redis (queue +     │
              │  embedding cache)   │
              └──┬──────────────┬───┘
                 │              │
          ┌──────▼───┐  ┌──────▼──────┐
          │ Embedding │  │  Crawler    │
          │ Worker    │  │  Worker     │
          └──────────┘  └─────────────┘
```

> **Note:** The search-api does **not** load the embedding model. Query embeddings
> are delegated to the embedding-worker via Celery and cached in Redis (default 1 hour TTL).

**Services started by Docker Compose:**

| Service | Port | Purpose |
|---------|------|---------|
| `postgres` | 5432 | PostgreSQL 16 + pgvector for data & vector storage |
| `redis` | 6379 | Cache, task queue broker |
| `search-api` (x2) | 8000 (internal) | Collection management & search endpoints |
| `ingestion-api` | 8001 (internal) | Document ingestion endpoints |
| `embedding-worker` | — | Celery worker for vector embedding generation (model baked in at build time) |
| `crawler-worker` | — | Celery worker for web crawling |
| `scheduler` | — | Celery beat for scheduled tasks |
| `nginx` | **80** | Gateway / reverse proxy (entry point) |

## Quick Start

### Prerequisites

- Docker & Docker Compose v2+
- Git

### 1. Clone and configure

```bash
git clone <your-repo-url> Semantic-Search-as-service
cd Semantic-Search-as-service
cp .env.example .env
```

Edit `.env` if needed — the defaults work for local development.

### 2. Start all services

```bash
docker compose up --build -d
```

### 3. Run database migrations

```bash
docker compose exec search-api alembic upgrade head
```

### 4. Verify

```bash
curl http://localhost/health
# {"status": "healthy", "version": "1.0.0"}
```

Swagger UI is available at [http://localhost/docs](http://localhost/docs).

## API Reference

All endpoints are prefixed with `/api/v1`. Authentication is via `Authorization: Bearer <api_key>` header.

### Collections

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| `POST` | `/collections` | master | Create a new collection |
| `GET` | `/collections` | any | List all collections |
| `GET` | `/collections/{id}` | any | Get collection details |
| `PATCH` | `/collections/{id}` | master | Update collection settings |
| `DELETE` | `/collections/{id}` | master | Delete a collection |

### Documents

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| `POST` | `/collections/{id}/documents` | ingest | Ingest documents (batch, with upsert) |
| `GET` | `/collections/{id}/documents/{ext_id}` | any | Get a document by external ID |
| `DELETE` | `/collections/{id}/documents/{ext_id}` | ingest | Delete a document |

### Search

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| `POST` | `/collections/{id}/search` | search | Semantic, keyword, or hybrid search |
| `POST` | `/collections/{id}/suggest` | search | Autocomplete suggestions |

### Jobs & Webhooks

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| `GET` | `/jobs/{job_id}` | any | Check ingestion job status |
| `POST` | `/collections/{id}/webhooks` | master | Register a webhook |
| `POST` | `/collections/{id}/crawl` | master | Trigger a website crawl |

### Example: End-to-End Workflow

**Create a collection:**

```bash
curl -X POST http://localhost/api/v1/collections \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "products",
    "embedding_model": "bge-m3",
    "chunk_strategy": "adaptive"
  }'
```

**Ingest documents:**

```bash
curl -X POST "http://localhost/api/v1/collections/$COLLECTION_ID/documents" \
  -H "Authorization: Bearer $INGEST_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "external_id": "doc_1",
        "content": "Your document text here",
        "title": "Document Title",
        "metadata": {"category": "example"}
      }
    ],
    "upsert": true
  }'
```

**Search:**

```bash
curl -X POST "http://localhost/api/v1/collections/$COLLECTION_ID/search" \
  -H "Authorization: Bearer $SEARCH_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "your search query",
    "mode": "hybrid",
    "limit": 10,
    "highlight": true
  }'
```

## Configuration

Environment variables (set in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async database connection string |
| `DATABASE_URL_SYNC` | `postgresql://...` | Sync connection string (Celery workers) |
| `DB_PASSWORD` | `changeme` | PostgreSQL password |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `SECRET_KEY` | — | Secret key for token signing |
| `DEBUG` | `false` | Enable debug logging |
| `DEFAULT_EMBEDDING_MODEL` | `bge-m3` | Sentence-transformer model for embeddings |
| `EMBEDDING_BATCH_SIZE` | `32` | Batch size for embedding generation |
| `EMBEDDING_DEVICE` | `cpu` | `cpu` or `cuda` for GPU acceleration |
| `EMBEDDING_CACHE_TTL` | `3600` | Seconds to cache query embeddings in Redis |
| `EMBEDDING_QUERY_TIMEOUT` | `30` | Seconds to wait for embedding-worker response |
| `RATE_LIMIT_ENABLED` | `true` | Enable per-key rate limiting |
| `MAX_CRAWL_PAGES` | `500` | Max pages per crawl job |
| `CRAWL_DELAY_SECONDS` | `1.0` | Delay between crawl requests |

## Project Structure

```
Semantic-Search-as-service/
├── app/
│   ├── api/v1/             # Route handlers (collections, documents, search, webhooks, jobs)
│   ├── core/               # Config, database, auth, rate limiting, Redis
│   ├── models/             # SQLAlchemy ORM models (8 tables)
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # Business logic (search, chunking, embedding, collections)
│   ├── workers/            # Celery tasks (embedding pipeline, crawler)
│   ├── main.py             # Search API FastAPI application
│   └── ingest.py           # Ingestion API FastAPI application
├── docker/
│   ├── Dockerfile.api      # API & scheduler image
│   ├── Dockerfile.gpu      # Embedding worker image (pre-baked model, GPU support)
│   └── Dockerfile.crawler  # Crawler worker image
├── migrations/versions/    # Alembic database migrations
├── nginx/conf.d/           # Nginx reverse proxy configuration
├── tests/                  # pytest test suite
├── .env.example            # Environment variable template
├── docker-compose.yml      # Full stack orchestration
├── requirements.txt        # Python dependencies
└── pyproject.toml          # Project metadata & tool config
```

## Database Schema

The platform uses 8 core tables with pgvector for vector storage:

- **organizations** — Multi-tenant organization accounts
- **api_keys** — Scoped API keys (master, ingest, search) with rate limits
- **collections** — Search collections with configurable embedding models and chunking strategies
- **documents** — Ingested documents with content, metadata, and processing status
- **chunks** — Document chunks produced by the chunking service
- **embeddings** — Vector embeddings stored via pgvector for ANN search
- **ingestion_jobs** — Async job tracking for document ingestion
- **search_logs** — Query analytics (query text, latency, result counts)

## Testing

```bash
# Inside Docker
docker compose exec search-api pytest tests/ -v

# Locally (Python 3.11+)
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

## Stopping Services

```bash
# Stop all services (preserves data)
docker compose down

# Stop and delete all data
docker compose down -v
```

## System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 8 GB | 16 GB |
| Disk | 15 GB free | 25 GB free |
| CPU | 4 cores | 8 cores |
| GPU | Not required | NVIDIA GPU for faster embedding |
