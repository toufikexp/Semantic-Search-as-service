# SkillConnect — Semantic Search Platform
## Handover & Reference Guide

> **Status:** Test phase on the production server.
> **Audience:** SkillConnect Dev team + HR team.
> **Purpose:** Everything needed to run tests, integrate, troubleshoot and make changes safely.

---

## Table of Contents

1. [System overview](#1-system-overview)
2. [Access & credentials](#2-access--credentials)
3. [PART A — For the HR team](#part-a--for-the-hr-team)
4. [PART B — For the Dev team (API reference)](#part-b--for-the-dev-team-api-reference)
5. [Operations — daily commands](#5-operations--daily-commands)
6. [Troubleshooting](#6-troubleshooting)
7. [Known limitations (test phase)](#7-known-limitations-test-phase)
8. [Making changes safely](#8-making-changes-safely)
9. [Escalation & contacts](#9-escalation--contacts)

---

## 1. System overview

Two separate applications running on the same server, connected through one nginx gateway.

```
                    HR Platform (SkillConnect)
                             │
                             ▼
                    ┌────────────────┐
                    │     nginx      │  port 80 — single entry point
                    └───────┬────────┘
              ┌─────────────┴──────────────┐
              ▼                            ▼
   ┌──────────────────────┐    ┌──────────────────────┐
   │  CV Intelligence     │    │  Semantic Search     │
   │  Layer (cv-api)      │───▶│  (search + ingest)   │
   │                      │◀───│                      │
   │  • parse CV (Gemini) │ webhook  • chunk text     │
   │  • OCR scanned PDFs  │          • embed (BGE-M3) │
   │  • candidate CRUD    │          • search engine  │
   └──────────────────────┘    └──────────────────────┘
```

**What each part does:**

| Component | Responsibility |
|---|---|
| **CV Intelligence Layer** | Receives CV files (PDF), extracts text (OCR if scanned), parses structured profile via Google Gemini, stores candidates, forwards text to Semantic Search |
| **Semantic Search** | Splits text into chunks, generates vector embeddings, provides semantic / keyword / hybrid search |
| **nginx** | Single gateway — routes requests to the right app, applies rate limits |

**Key concept — everything is asynchronous.** When you submit a CV or document, the API returns immediately with a `job_id`. The actual processing (embedding) happens in the background and takes a few seconds. **A document is not searchable until its status becomes `indexed`.**

### Technology used

| Layer | Technology |
|---|---|
| APIs | FastAPI (Python 3.11) |
| Database | PostgreSQL 16 + pgvector |
| Queue / cache | Redis 7 + Celery |
| Embedding model | **BAAI/bge-m3** (1024 dimensions, multilingual: AR/FR/EN) |
| CV parsing | Google Gemini API |
| OCR | EasyOCR |
| Gateway | nginx |
| Deployment | Docker Compose |

---

## 2. Access & credentials

### Base URL

```
http://<server-ip>          # all APIs go through nginx on port 80
```

> ⚠️ **No HTTPS yet in test phase.** See [Known limitations](#7-known-limitations-test-phase).

### API keys — 3 scope levels

Every request needs a header:
```
Authorization: Bearer <api_key>
```

| Scope | Key prefix | Can do |
|---|---|---|
| `master` | `sk_master_` | Everything: create/delete collections, ingest, search, crawl |
| `ingest` | `sk_ingest_` | Add / delete documents in its own collection only |
| `search` | `sk_search_` | Search + suggest in its own collection only |

**Important rules:**
- Keys are stored **hashed** (SHA-256). The raw key is shown **only once**, at creation. If lost, it cannot be recovered — a new key must be issued.
- `ingest` and `search` keys are **bound to one collection**. Using them on another collection returns `403 FORBIDDEN`.
- Store keys in a password manager, never in Git, never in frontend code.

### Where keys come from

Creating a collection automatically returns its `ingest` and `search` keys — see [Dev team section](#step-1--create-a-collection).

---

# PART A — For the HR team

*This section is non-technical. It explains what to test and what to expect.*

## A.1 What you are testing

You are testing whether the system can:
1. Accept CVs (PDF upload or text)
2. Understand their content in **Arabic, French and English**
3. Let you find the right candidates using **natural language** — not just exact keywords

## A.2 The key difference from normal search

| Classic keyword search | This system (semantic search) |
|---|---|
| Searching "developer" finds only CVs containing the exact word "developer" | Searching "developer" also finds "développeur", "programmer", "software engineer" |
| Searching "5 years experience" matches the literal text | Understands meaning and finds equivalent phrasing |

**Search modes available:**

| Mode | What it does | When to use |
|---|---|---|
| `hybrid` ⭐ | Combines meaning + exact keywords | **Default — use this** |
| `semantic` | Pure meaning-based | Conceptual searches ("someone who can lead a team") |
| `keyword` | Exact words only | Finding a specific name, reference number or exact skill |

## A.3 Test scenarios to run

Please test and record results for:

| # | Scenario | What to check |
|---|---|---|
| 1 | Upload a **text-based PDF** CV | Name, skills, experience extracted correctly? |
| 2 | Upload a **scanned/photo** CV | Does OCR read it? (slower — up to 60s) |
| 3 | Upload an **Arabic** CV | Text extracted? Searchable in Arabic? |
| 4 | Upload a **French** CV | Text extracted? Searchable in French? |
| 5 | Search a job title in French, expect English CVs to match | Cross-language matching works? |
| 6 | Search a skill ("Kubernetes", "comptabilité") | Relevant candidates on top? |
| 7 | Search a full sentence ("ingénieur réseau avec expérience télécom") | Sensible ranking? |
| 8 | Re-upload the same candidate with updated CV | Old version replaced, not duplicated? |
| 9 | Delete a candidate | Disappears from search results? |
| 10 | Search immediately after upload | *Expected:* not found for a few seconds — this is normal |

### What to report when something looks wrong

Please include:
- The **exact search text** you typed
- The **candidate/CV** you expected to find
- What you got instead (screenshot)
- Approximate **time** of the test (for log lookup)

## A.4 Things that are normal (not bugs)

| Observation | Explanation |
|---|---|
| A CV is not searchable immediately after upload | Processing takes ~2–10 seconds (longer for scanned PDFs). This is by design. |
| Scanned CVs take much longer | OCR is slow, especially without a graphics card. Up to ~60s. |
| Arabic search results are less precise than French/English | Known limitation in test phase — Arabic language support is reduced (see §7) |
| Results have a "score" | Relevance score, higher = better match. Not a percentage. |
| Search returns fewer results than expected | Only **fully processed** CVs appear. Check the candidate's status first. |

## A.5 Glossary

| Term | Meaning |
|---|---|
| **Collection** | A container/folder for documents. E.g. one collection for all CVs. |
| **Document** | One CV (or one web page) stored in the system. |
| **Chunk** | A CV is cut into smaller pieces so search can match a precise section. |
| **Embedding** | A numeric representation of meaning — this is what makes semantic search work. |
| **Indexed** | Status meaning "fully processed and searchable". |
| **Job** | A background processing task. Has an ID you can check for progress. |
| **external_id** | Your own reference for a candidate (e.g. `CAND-2026-0042`). You choose it. |

---

# PART B — For the Dev team (API reference)

## B.1 Golden rules

1. **Ingestion is asynchronous.** `POST /documents` returns `202` + a `job_id`. The document is **not searchable yet**.
2. **Poll the job** (`GET /jobs/{job_id}`) or **listen for the webhook** to know when it's done.
3. **Only documents with `status: "indexed"` appear in search results.**
4. **Upsert by `external_id`.** Re-posting the same `external_id` replaces the previous version (content, chunks, embeddings).
5. **Never put an API key in frontend code.** Your backend must proxy the calls.

## B.2 Endpoint map

All paths are prefixed `/api/v1`.

### Semantic Search endpoints

| Method | Path | Scope | Notes |
|---|---|---|---|
| `POST` | `/collections` | master | Creates collection **+ returns its 2 keys** |
| `GET` | `/collections` | any | List collections |
| `GET` | `/collections/{id}` | any | Collection detail + `doc_count` |
| `PATCH` | `/collections/{id}` | master | Update settings / `callback_url` |
| `DELETE` | `/collections/{id}` | master | ⚠️ Deletes all data in it |
| `POST` | `/collections/{id}/documents` | ingest | **Ingest** — returns `202` + `job_id` |
| `GET` | `/collections/{id}/documents/{external_id}` | any | Document status |
| `DELETE` | `/collections/{id}/documents/{external_id}` | ingest | Returns `204` |
| `POST` | `/collections/{id}/search` | search | **Search** |
| `POST` | `/collections/{id}/suggest` | search | Autocomplete |
| `GET` | `/jobs/{job_id}` | any | Job progress |
| `POST` | `/collections/{id}/crawl` | master | Crawl a website into the collection |
| `GET` | `/health` | none | Health check |
| `GET` | `/docs` | none | Interactive Swagger UI |

### CV Intelligence Layer endpoints (through the same gateway)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v1/candidates/upload` | Upload CV file (PDF) |
| `POST` | `/api/v1/candidates/extract` | Extract only — no storage |
| `POST` | `/api/v1/candidates` | Create candidate from JSON |
| `GET/PUT/PATCH/DELETE` | `/api/v1/candidates/{cv_id}` | Candidate CRUD |
| `GET` | `/api/v1/candidates/{cv_id}/status` | Processing status |
| `POST` | `/api/v1/candidates/search` | Candidate search |
| `GET/PUT/PATCH/DELETE` | `/api/v1/collections/{id}/candidates/{external_id}` | CRUD by **your** business key |
| `GET` | `/ready` | CV layer readiness |

> **Note:** `/health` belongs to Semantic Search. The CV layer uses **`/ready`**.

## B.3 Integration flow — end to end

```
1. POST /api/v1/candidates/upload         (CV layer)
        │  extracts text, parses with Gemini
        ▼
2. CV layer calls Semantic Search internally
   POST /api/v1/collections/{id}/documents  →  202 + job_id
        │
        ▼
3. Background worker: chunk → embed (BGE-M3) → index
        │
        ▼
4. Webhook fired to the collection's callback_url
   POST /api/webhooks/ingestion   (signed HMAC-SHA256)
        │
        ▼
5. Candidate is now searchable
   POST /api/v1/collections/{id}/search
```

## B.4 Working examples

### Setup

```bash
BASE=http://<server-ip>
MASTER=sk_master_xxxxxxxxxxxxxxxx
```

### Step 1 — Create a collection

```bash
curl -s -X POST "$BASE/api/v1/collections" \
  -H "Authorization: Bearer $MASTER" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "skillconnect-cvs",
    "description": "Candidate CVs",
    "language": "fr",
    "chunk_strategy": "adaptive",
    "chunk_size": 512,
    "chunk_overlap": 50,
    "callback_url": "http://nginx/api/webhooks/ingestion",
    "callback_secret": "<shared-secret>"
  }' | python3 -m json.tool
```

**Response contains the only copy of your two keys — save them now:**
```json
{
  "id": "dd8aa5b5-7b2a-4e1c-9f0d-1a2b3c4d5e6f",
  "name": "skillconnect-cvs",
  "status": "active",
  "api_keys": {
    "ingest": "sk_ingest_...",
    "search": "sk_search_..."
  }
}
```

```bash
COLL=dd8aa5b5-7b2a-4e1c-9f0d-1a2b3c4d5e6f
INGEST=sk_ingest_...
SEARCH=sk_search_...
```

### Step 2 — Ingest documents

```bash
curl -s -X POST "$BASE/api/v1/collections/$COLL/documents" \
  -H "Authorization: Bearer $INGEST" \
  -H "Content-Type: application/json" \
  -d '{
    "upsert": true,
    "documents": [
      {
        "external_id": "CAND-2026-0042",
        "title": "Sarah Benali - Senior Backend Engineer",
        "content_type": "text",
        "content": "Sarah Benali. Ingénieure backend senior. 8 ans Python, FastAPI, PostgreSQL, Docker. Master informatique USTHB Alger.",
        "url": "https://hr.internal/cvs/CAND-2026-0042.pdf",
        "metadata": {
          "candidate_id": "cand_7788",
          "department": "engineering",
          "location": "Algiers",
          "years_experience": 8
        }
      }
    ]
  }'
```

Response (**HTTP 202**):
```json
{ "job_id": "7a1f2e9b-...", "documents_queued": 1, "status": "processing" }
```

**Limits:** max **1000 documents** per request. Nginx body limit **100 MB** on this route.

### Step 3 — Wait for processing

**Option A — poll the job:**
```bash
curl -s "$BASE/api/v1/jobs/$JOB" -H "Authorization: Bearer $INGEST"
```
```json
{ "status": "completed", "total_docs": 1, "processed_docs": 1, "failed_docs": 0 }
```

| Job status | Meaning |
|---|---|
| `processing` | Still running |
| `completed` | All documents indexed ✅ |
| `completed_with_errors` | Some failed — check `errors` field |
| `failed` | Job failed entirely |

**Option B — check one document:**
```bash
curl -s "$BASE/api/v1/collections/$COLL/documents/CAND-2026-0042" \
  -H "Authorization: Bearer $INGEST"
```
Look for `"status": "indexed"` and `chunk_count > 0`.

**Option C — webhook** (recommended for production): see §B.6.

### Step 4 — Search

```bash
curl -s -X POST "$BASE/api/v1/collections/$COLL/search" \
  -H "Authorization: Bearer $SEARCH" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "ingénieur backend Python expérimenté",
    "mode": "hybrid",
    "limit": 10
  }' | python3 -m json.tool
```

**Full request options:**

| Field | Type | Default | Notes |
|---|---|---|---|
| `query` | string | **required** | The search text |
| `mode` | string | `hybrid` | `hybrid` \| `semantic` \| `keyword` |
| `limit` | int | 20 | 1–100 |
| `offset` | int | 0 | Pagination |
| `filters` | object | `{}` | Exact match on metadata, e.g. `{"department":"engineering"}` |
| `facets` | array | `[]` | Count aggregation, e.g. `["department","location"]` |
| `min_score` | float | 0.0 | 0.0–1.0 relevance threshold |
| `highlight` | bool | true | Return matched snippets |

**Response:**
```json
{
  "results": [
    {
      "doc_id": "uuid",
      "external_id": "CAND-2026-0042",
      "score": 0.87,
      "title": "Sarah Benali - Senior Backend Engineer",
      "url": "https://...",
      "highlights": ["...<em>Python</em>, FastAPI..."],
      "metadata": {"department": "engineering"}
    }
  ],
  "facets": {},
  "total": 1,
  "query_id": "uuid",
  "took_ms": 48
}
```

### Step 5 — Delete

```bash
curl -s -X DELETE "$BASE/api/v1/collections/$COLL/documents/CAND-2026-0042" \
  -H "Authorization: Bearer $INGEST" -w "\nHTTP %{http_code}\n"
```
Returns `204`. Cascade-deletes chunks and embeddings.

## B.5 How search actually works (for tuning expectations)

| Mode | Mechanism |
|---|---|
| `semantic` | Vector cosine similarity via pgvector HNSW index |
| `keyword` | PostgreSQL full-text search (`tsvector` / `ts_rank`) |
| `hybrid` | Both, fused with weighted Reciprocal Rank Fusion — **vector 0.7 / keyword 0.3**, k=60 |

**Chunking** (configured per collection):

| Strategy | Behaviour |
|---|---|
| `adaptive` ⭐ default | Splits on headings, sub-splits long sections by paragraph |
| `fixed` | Sliding window by size with overlap |
| `sentence` | Splits at sentence boundaries |
| `paragraph` | Splits at blank lines |

Default `chunk_size` = **512 tokens**, `chunk_overlap` = **50**.

## B.6 Webhook (ingestion completed)

When a job finishes, the platform POSTs to the collection's `callback_url`.

**Payload:**
```json
{
  "event": "ingestion.completed",
  "job_id": "7a1f2e9b-...",
  "collection_id": "dd8aa5b5-...",
  "status": "completed",
  "total_docs": 2,
  "processed_docs": 2,
  "failed_docs": 0,
  "documents": [
    {"external_id": "CAND-2026-0042", "status": "indexed"},
    {"external_id": "CAND-2026-0043", "status": "failed", "error": "..."}
  ],
  "completed_at": "2026-04-09T12:11:33Z"
}
```

**Security — HMAC signature:**
- Header: `X-Webhook-Signature`
- Value: `HMAC-SHA256(callback_secret, raw_request_body)` in hex
- ⚠️ **The secret itself is never transmitted.** Your receiver must recompute the HMAC over the raw body and compare.

**Verification example (Python):**
```python
import hmac, hashlib

def verify(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

**Delivery behaviour:** up to **3 attempts**, **10s timeout** each. Any `2xx` = acknowledged. Failures are logged but do **not** affect the ingestion — data is already indexed before the callback fires.

## B.7 Error format

All errors use this envelope:
```json
{ "error": { "code": "ERROR_CODE", "message": "...", "request_id": "uuid" } }
```

| HTTP | Code | Cause | Fix |
|---|---|---|---|
| 401 | `UNAUTHORIZED` | Missing/invalid key, or wrong header format | Use `Authorization: Bearer sk_...` |
| 403 | `FORBIDDEN` | Key lacks scope, or key not bound to this collection | Use the right key for that collection |
| 404 | `COLLECTION_NOT_FOUND` / `NOT_FOUND` | Wrong ID | Verify the UUID |
| 422 | validation error | Malformed body | Check required fields |
| 429 | `RATE_LIMITED` | Too many requests | Back off, retry |
| 503 | `EMBEDDING_UNAVAILABLE` | Embedding worker down/busy (semantic mode only) | Use `hybrid` (auto-falls back) or restart worker |

## B.8 Rate limits (nginx, per client IP)

| Route | Rate | Burst |
|---|---|---|
| `/api/v1/collections*` (search) | 100 req/s | 50 |
| `/documents`, `/webhooks`, `/crawl` | 20 req/s | 10–20 |
| `/api/v1/candidates*` (CV layer) | 200 req/s | 200 |

Exceeding these returns **503** from nginx (not 429). If you hit this during bulk tests, throttle client-side or raise the limit in `nginx/conf.d/default.conf`.

---

## 5. Operations — daily commands

Run from the project directory on the server.

```bash
cd /opt/semantic-search        # or wherever the repo is deployed
```

### Status & health

```bash
docker compose ps                              # all containers + health
curl -s http://localhost/health                # Semantic Search
curl -s http://localhost/ready                 # CV layer
curl -s http://localhost/nginx-health          # nginx itself
```

### Logs

```bash
docker compose logs -f --tail 100 search-api         # search API
docker compose logs -f --tail 100 ingestion-api      # ingestion API
docker compose logs -f --tail 100 embedding-worker   # ⭐ processing / embedding
docker compose logs -f --tail 100 nginx              # routing / 502 errors
docker compose logs -f --tail 100 postgres
```

> The **embedding-worker** log is the most useful one — it shows chunking, embedding and webhook delivery.

### Restart

```bash
docker compose restart nginx                    # after nginx config change
docker compose restart embedding-worker         # if processing is stuck
docker compose up -d                            # apply compose changes
docker compose up -d --no-deps --build search-api   # rebuild one service
```

### Services reference

| Service | Role | Port |
|---|---|---|
| `nginx` | Gateway | **80** (public) |
| `search-api` (×2) | Search API | 8000 |
| `ingestion-api` | Ingestion API | 8001 |
| `embedding-worker` | Chunking + embedding (Celery) | — |
| `crawler-worker` | Website crawling (Celery) | — |
| `scheduler` | Scheduled cleanup (Celery beat) | — |
| `postgres` | Database | 5432 |
| `redis` | Cache + queue | 6379 |

### Database access

```bash
# via container
docker compose exec postgres psql -U postgres -d semantic_search

# useful queries
SELECT status, COUNT(*) FROM documents GROUP BY status;
SELECT id, status, total_docs, processed_docs, failed_docs, created_at
  FROM ingestion_jobs ORDER BY created_at DESC LIMIT 10;
SELECT COUNT(*) FROM embeddings;
SELECT query, mode, latency_ms, results_count, created_at
  FROM search_logs ORDER BY created_at DESC LIMIT 20;
```

DBeaver / external tools connect to `<server-ip>:5432`, database `semantic_search`.

### Migrations

```bash
docker compose exec search-api alembic upgrade head    # apply
docker compose exec search-api alembic current         # check version
```

---

## 6. Troubleshooting

### 🔴 502 Bad Gateway on every endpoint

**Most common issue.** nginx caches upstream IPs at startup. When an app container is recreated it gets a new IP, and nginx keeps using the old one.

```bash
docker compose restart nginx
```

This is **not** a code problem. Any time you recreate `search-api`, `ingestion-api` or `cv-api`, **restart nginx afterwards**.

### 🔴 Documents stuck in `pending` / job stays `processing`

```bash
# 1. Is the worker alive?
docker compose ps embedding-worker
docker compose logs --tail 100 embedding-worker

# 2. Is the queue backed up?
docker compose exec redis redis-cli LLEN embeddings

# 3. Restart the worker
docker compose restart embedding-worker
```

If documents remain stuck after a restart, re-queue them:
```bash
docker compose exec search-api python scripts/reprocess_pending.py
```

### 🔴 Search returns nothing for a document you just added

Expected if processing hasn't finished. Verify:
```bash
curl -s "$BASE/api/v1/collections/$COLL/documents/<external_id>" \
  -H "Authorization: Bearer $INGEST"
```
- `"status": "pending"` → still processing, wait
- `"status": "failed"` → check embedding-worker logs
- `"status": "indexed"` but not found → check you're searching the right collection and your `filters` aren't excluding it

### 🔴 503 `EMBEDDING_UNAVAILABLE` on semantic search

The embedding worker is down or the query timed out (10s limit).

```bash
docker compose restart embedding-worker
```
Workaround: use `mode: "hybrid"` — it automatically falls back to keyword search instead of failing.

### 🔴 Webhook returns 401 at the CV layer

Semantic Search sends the `X-Webhook-Signature` header (HMAC) but **no `Authorization` header**. If the CV layer's webhook endpoint requires bearer auth, it will reject with 401.

**Fix (CV layer side):** the `/api/webhooks/ingestion` endpoint must be exempt from bearer auth and instead verify the HMAC signature (see §B.6).

### 🔴 503 from nginx during bulk testing

You hit the nginx rate limit — not an application error. Throttle the client, or raise the limits in `nginx/conf.d/default.conf` then `docker compose restart nginx`.

### 🔴 403 FORBIDDEN

The key doesn't have the required scope, **or** it's an `ingest`/`search` key bound to a different collection. Verify which collection the key belongs to.

### Diagnostic checklist

```bash
docker compose ps                                    # 1. all healthy?
curl -s http://localhost/health                      # 2. app responding?
docker compose logs --tail 50 embedding-worker       # 3. worker processing?
docker compose exec postgres psql -U postgres -d semantic_search \
  -c "SELECT status, COUNT(*) FROM documents GROUP BY status;"   # 4. doc states
```

---

## 7. Known limitations (test phase)

Be aware of these when interpreting test results. They are **known**, documented, and scheduled.

| # | Limitation | Impact | Status |
|---|---|---|---|
| 1 | **No HTTPS/TLS** — traffic is plain HTTP on port 80 | CV data travels unencrypted | ⚠️ Must fix before production |
| 2 | **No question-answering (RAG)** | System returns ranked documents, **not** generated answers | Not implemented |
| 3 | **French keyword search is slow** — the full-text index covers `english` and `simple` only, so a `french` collection scans every row | Slow keyword/hybrid search as data grows | Fix = add French FTS index |
| 4 | **Arabic has no stemming** — falls back to `simple` tokenisation | Lower recall for Arabic keyword search. Semantic (vector) search still works well for Arabic. | Known trade-off |
| 5 | **Application-level rate limiting is not active** — only nginx per-IP limits | Per-API-key quotas not enforced | Code exists but is not wired |
| 6 | **API key lookup hits the database on every request** | Extra DB load at high traffic | Fine at test scale |
| 7 | **CPU-only embedding** (no GPU) | Scanned CV / bulk processing is slow | Acceptable for test volumes |
| 8 | **Search logs write one row per query** | Table grows; auto-cleanup after 90 days | Monitor size |
| 9 | **Scanned PDFs are much slower** (OCR) | Up to ~60s per CV | Expected |

---

## 8. Making changes safely

### Before any change

```bash
cd /opt/semantic-search
git status                 # confirm clean
git pull origin <branch>   # get latest
```

### Changing nginx routing or rate limits

```bash
vim nginx/conf.d/default.conf
docker compose exec nginx nginx -t      # ALWAYS validate syntax first
docker compose restart nginx
curl -s http://localhost/health         # verify
```

### Changing application code

```bash
docker compose build search-api ingestion-api embedding-worker
docker compose up -d
docker compose restart nginx            # ⚠️ don't forget — avoids 502
```

### Changing environment variables

```bash
vim .env
docker compose up -d                    # recreates affected containers
```

### Changing collection settings (e.g. callback_url)

```bash
curl -s -X PATCH "$BASE/api/v1/collections/$COLL" \
  -H "Authorization: Bearer $MASTER" \
  -H "Content-Type: application/json" \
  -d '{"callback_url": "http://nginx/api/webhooks/ingestion"}'
```

### ⚠️ Dangerous operations — never run without approval

| Command | Consequence |
|---|---|
| `docker compose down -v` | **Deletes the database volume — all data lost** |
| `DELETE /api/v1/collections/{id}` | Deletes the collection and every document in it |
| `docker volume rm ...pgdata` | Destroys the database |
| `docker system prune --volumes` | Destroys all volumes |

`docker compose down` **without** `-v` is safe — data survives in volumes.

### Rollback

```bash
git log --oneline -5
git checkout <previous-commit> -- <file>
docker compose build && docker compose up -d
docker compose restart nginx
```

### Backups

Database is backed up by the infrastructure backup team (VM + DB, daily, 7–30 day retention).
Manual dump before a risky change:
```bash
docker compose exec -T postgres pg_dump -U postgres -Fc semantic_search \
  > /backups/pre-change-$(date +%F-%H%M).dump
```

---

## 9. Escalation & contacts

### Before escalating, collect:

1. **What you did** — exact request (curl command or endpoint + payload)
2. **What you expected** vs **what happened** (full error response)
3. **Timestamp** of the incident
4. **Logs:**
   ```bash
   docker compose logs --since 30m --tail 200 search-api > /tmp/search-api.log
   docker compose logs --since 30m --tail 200 embedding-worker > /tmp/worker.log
   docker compose ps > /tmp/status.txt
   ```
5. **`request_id`** from the error response, if present

### Quick triage

| Symptom | First action |
|---|---|
| Everything returns 502 | `docker compose restart nginx` |
| Nothing gets indexed | `docker compose restart embedding-worker` |
| Search slow | Check `search_logs.latency_ms`, check worker load |
| Specific document failed | Check `embedding-worker` logs for its `external_id` |
| CV upload fails | Check CV layer logs + Gemini API connectivity |

### Reference links

| Resource | URL |
|---|---|
| Interactive API docs (Swagger) | `http://<server-ip>/docs` |
| OpenAPI spec | `http://<server-ip>/openapi.json` |
| Prometheus metrics | `http://<server-ip>/metrics` |
| Architecture & code map | `CLAUDE.md` in the repo |
| Setup guide | `SETUP.md` in the repo |

---

*Document version 1.0 — test phase. Update this file as issues are resolved.*
