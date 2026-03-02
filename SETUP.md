# Semantic Search API - Setup & Run Guide

> Setup instructions for **WSL Ubuntu on Windows**

---

## 1. Machine Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 8 GB | 16 GB |
| Disk | 10 GB free | 20 GB free |
| CPU | 4 cores | 8 cores |
| GPU | Not required (CPU mode) | NVIDIA GPU for faster embedding |
| OS | WSL 2 + Ubuntu 22.04/24.04 | Same |

---

## 2. Prerequisites

### 2.1 Docker Desktop for Windows (with WSL 2 backend)

Docker is used to run all services (database, Redis, API, workers). Install Docker Desktop on Windows, then enable the WSL 2 integration.

**Steps:**

1. Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. During setup choose **"Use WSL 2 instead of Hyper-V"**
3. After install, open Docker Desktop → **Settings → Resources → WSL Integration**
4. Toggle ON your Ubuntu distro
5. Verify from inside your WSL terminal:

```bash
docker --version       # should print Docker version 24+
docker compose version # should print v2.x
```

### 2.2 Git

Pre-installed on Ubuntu WSL. Verify:

```bash
git --version
```

### 2.3 (Optional) Python 3.11+ for local development without Docker

Only needed if you want to run the API outside containers.

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip
```

---

## 3. Clone the Repository

```bash
git clone <your-repo-url> Semantic-Search-as-service
cd Semantic-Search-as-service
```

---

## 4. Configure Environment Variables

Copy the example env file and review the defaults:

```bash
cp .env.example .env
```

The `.env` file contents:

```dotenv
# Database
DATABASE_URL=postgresql+asyncpg://postgres:changeme@localhost:5432/semantic_search
DATABASE_URL_SYNC=postgresql://postgres:changeme@localhost:5432/semantic_search
DB_PASSWORD=changeme

# Redis
REDIS_URL=redis://localhost:6379/0

# API
API_HOST=0.0.0.0
API_PORT=8000
SECRET_KEY=your-secret-key-change-in-production
DEBUG=true

# Embedding
DEFAULT_EMBEDDING_MODEL=bge-m3
EMBEDDING_BATCH_SIZE=32
EMBEDDING_DEVICE=cpu

# Rate Limiting
RATE_LIMIT_ENABLED=true

# Crawling
MAX_CRAWL_PAGES=500
CRAWL_DELAY_SECONDS=1.0
```

For a demo, the defaults work fine. If you want to change the DB password, update `DB_PASSWORD` (Docker Compose reads it automatically).

---

## 5. Run with Docker Compose (Recommended)

This single command builds and starts all 7 services:

```bash
docker compose up --build -d
```

**What gets started:**

| Service | Port | Purpose |
|---------|------|---------|
| `postgres` | 5432 | PostgreSQL 16 + pgvector |
| `redis` | 6379 | Cache & task queue |
| `search-api` (x2 replicas) | 8000 (internal) | Search & collection endpoints |
| `ingestion-api` | 8001 (internal) | Document ingestion endpoints |
| `embedding-worker` | - | Celery worker for embedding generation |
| `crawler-worker` | - | Celery worker for web crawling |
| `scheduler` | - | Celery beat for scheduled tasks |
| `nginx` | **80** | Gateway / reverse proxy (your entry point) |

Wait about 30-60 seconds for the first build and for PostgreSQL to become healthy.

Check that everything is running:

```bash
docker compose ps
```

You should see all containers with status `running` or `healthy`.

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f search-api
docker compose logs -f embedding-worker
```

---

## 6. Run Database Migrations

After the containers are up, run the Alembic migration to create all tables:

```bash
docker compose exec search-api alembic upgrade head
```

This creates: `organizations`, `collections`, `api_keys`, `documents`, `chunks`, `embeddings`, `ingestion_jobs`, `search_logs` — and enables the `vector`, `pg_trgm`, and `btree_gin` PostgreSQL extensions.

---

## 7. Verify the Setup

### Health Check

```bash
curl http://localhost/health
```

Expected response:

```json
{"status": "healthy", "version": "1.0.0"}
```

### API Docs (Swagger UI)

Open in your Windows browser:

```
http://localhost/docs
```

---

## 8. Quick Demo Walkthrough

### Step 1 - Seed an Organization and Master API Key

Connect to the database and insert a test org + master key:

```bash
docker compose exec postgres psql -U postgres -d semantic_search
```

Inside psql:

```sql
-- Create a demo organization
INSERT INTO organizations (id, name, plan_tier)
VALUES ('11111111-1111-1111-1111-111111111111', 'Demo Org', 'pro');

-- Create a master API key (hash of "sk_master_demo_key_for_testing")
-- SHA-256 of that string = we'll use a known hash
INSERT INTO api_keys (org_id, key_hash, key_prefix, scope, rate_limit, is_active)
VALUES (
  '11111111-1111-1111-1111-111111111111',
  'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  'sk_master_',
  'master',
  600,
  true
);

\q
```

> **Note:** For the demo, we are inserting a well-known hash. In production, the API generates proper random keys via the `POST /api/v1/collections` endpoint.

To generate a real hash for any key string, run:

```bash
echo -n "your_raw_key_here" | sha256sum
```

Then use that hash in the INSERT.

### Step 2 - Create a Collection

```bash
curl -s -X POST http://localhost/api/v1/collections \
  -H "Authorization: Bearer sk_master_demo_key_for_testing" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "demo-products",
    "description": "Demo product catalog",
    "embedding_model": "bge-m3",
    "chunk_strategy": "adaptive",
    "metadata_schema": {
      "category": "string",
      "price": "float"
    }
  }' | python3 -m json.tool
```

The response contains the collection ID and scoped API keys for `ingest` and `search`.

### Step 3 - Ingest Documents

Use the collection ID and ingest key from the previous response:

```bash
COLLECTION_ID="<collection_id_from_response>"
INGEST_KEY="<sk_ingest_key_from_response>"

curl -s -X POST "http://localhost/api/v1/collections/${COLLECTION_ID}/documents" \
  -H "Authorization: Bearer ${INGEST_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "external_id": "prod_001",
        "content": "Nike Air Zoom Pegasus 40 is a lightweight cushioned running shoe designed for beginners and daily training. Features responsive foam and breathable mesh upper.",
        "title": "Nike Air Zoom Pegasus 40",
        "url": "https://example.com/products/001",
        "metadata": {"category": "running-shoes", "price": 89.99}
      },
      {
        "external_id": "prod_002",
        "content": "Adidas Ultraboost Light delivers incredible energy return with a BOOST midsole. Great for long distance running and everyday comfort.",
        "title": "Adidas Ultraboost Light",
        "url": "https://example.com/products/002",
        "metadata": {"category": "running-shoes", "price": 119.99}
      },
      {
        "external_id": "prod_003",
        "content": "New Balance Fresh Foam X 1080v13 provides plush cushioning for high mileage training. Supportive fit with engineered mesh.",
        "title": "New Balance Fresh Foam X 1080v13",
        "url": "https://example.com/products/003",
        "metadata": {"category": "running-shoes", "price": 159.99}
      }
    ],
    "upsert": true
  }' | python3 -m json.tool
```

Response returns a `job_id`. Check processing status:

```bash
JOB_ID="<job_id_from_response>"
curl -s "http://localhost/api/v1/jobs/${JOB_ID}" \
  -H "Authorization: Bearer ${INGEST_KEY}" | python3 -m json.tool
```

Wait a few seconds for the embedding worker to process.

### Step 4 - Search

```bash
SEARCH_KEY="<sk_search_key_from_response>"

curl -s -X POST "http://localhost/api/v1/collections/${COLLECTION_ID}/search" \
  -H "Authorization: Bearer ${SEARCH_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "lightweight running shoes for beginners",
    "mode": "hybrid",
    "limit": 10,
    "highlight": true,
    "facets": ["category"]
  }' | python3 -m json.tool
```

### Step 5 - Autocomplete

```bash
curl -s -X POST "http://localhost/api/v1/collections/${COLLECTION_ID}/suggest" \
  -H "Authorization: Bearer ${SEARCH_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"prefix": "Nike", "limit": 5}' | python3 -m json.tool
```

---

## 9. API Endpoints Reference

### Collections

| Method | Endpoint | Auth Scope | Description |
|--------|----------|------------|-------------|
| `POST` | `/api/v1/collections` | master | Create collection |
| `GET` | `/api/v1/collections` | any | List collections |
| `GET` | `/api/v1/collections/{id}` | any | Get collection details |
| `PATCH` | `/api/v1/collections/{id}` | master | Update collection |
| `DELETE` | `/api/v1/collections/{id}` | master | Delete collection |

### Documents

| Method | Endpoint | Auth Scope | Description |
|--------|----------|------------|-------------|
| `POST` | `/api/v1/collections/{id}/documents` | ingest | Ingest documents |
| `GET` | `/api/v1/collections/{id}/documents/{ext_id}` | any | Get document |
| `DELETE` | `/api/v1/collections/{id}/documents/{ext_id}` | ingest | Delete document |

### Search

| Method | Endpoint | Auth Scope | Description |
|--------|----------|------------|-------------|
| `POST` | `/api/v1/collections/{id}/search` | search | Execute search query |
| `POST` | `/api/v1/collections/{id}/suggest` | search | Autocomplete suggestions |

### Jobs & Webhooks

| Method | Endpoint | Auth Scope | Description |
|--------|----------|------------|-------------|
| `GET` | `/api/v1/jobs/{job_id}` | any | Check ingestion job status |
| `POST` | `/api/v1/collections/{id}/webhooks` | master | Register webhook |
| `POST` | `/api/v1/collections/{id}/crawl` | master | Trigger website crawl |

---

## 10. Running Tests

```bash
# Inside container
docker compose exec search-api pytest tests/ -v

# Or locally (requires Python 3.11 + venv)
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

---

## 11. Stopping & Cleanup

```bash
# Stop all services (keeps data)
docker compose down

# Stop and delete all data (volumes)
docker compose down -v
```

---

## 12. WSL-Specific Tips

| Issue | Fix |
|-------|-----|
| `docker: command not found` | Make sure Docker Desktop → Settings → Resources → WSL Integration has your distro enabled, then restart your WSL terminal |
| Port 80 already in use | Stop IIS or other web servers on Windows: `net stop w3svc` in PowerShell (Admin) |
| Slow file I/O | Keep the project inside the WSL filesystem (`~/projects/...`), not under `/mnt/c/` |
| Out of memory | Open `%USERPROFILE%/.wslconfig` on Windows and increase: `[wsl2]\nmemory=8GB` then `wsl --shutdown` |
| Cannot access `localhost` from browser | Use `http://localhost` in Windows browser — WSL 2 forwards ports automatically via Docker Desktop |

---

## 13. Project Structure

```
Semantic-Search-as-service/
├── app/
│   ├── api/v1/             # Route handlers (collections, documents, search, webhooks, jobs)
│   ├── core/               # Config, database, auth, rate limiting, Redis
│   ├── models/             # SQLAlchemy ORM models (8 tables)
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # Business logic (collection, document, search, chunking, embedding)
│   ├── workers/            # Celery tasks (embedding pipeline, crawler)
│   ├── main.py             # Search API FastAPI app
│   └── ingest.py           # Ingestion API FastAPI app
├── docker/
│   ├── Dockerfile.api      # API & scheduler image
│   ├── Dockerfile.gpu      # Embedding worker image
│   └── Dockerfile.crawler  # Crawler worker image
├── migrations/
│   └── versions/           # Alembic migration (initial schema with pgvector)
├── nginx/conf.d/           # Nginx reverse proxy config
├── tests/                  # pytest test suite
├── .env.example            # Environment variable template
├── docker-compose.yml      # Full stack orchestration
├── requirements.txt        # Python dependencies
└── pyproject.toml          # Project metadata & tool config
```
