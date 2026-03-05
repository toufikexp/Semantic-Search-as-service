"""End-to-end integration tests: ingest -> chunk -> embed -> search.

These tests verify the full pipeline works correctly by ingesting documents
into a real PostgreSQL + pgvector database and searching them.

Requires: running postgres and redis (docker compose up postgres redis).

Run with: pytest tests/integration/test_search_pipeline.py -v
Mark: @pytest.mark.integration
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import Document
from app.models.embedding import Embedding
from app.schemas.search import SearchRequest
from app.services.chunking_service import chunk_text
from app.services.embedding_service import compute_embeddings
from app.services.search_service import execute_search

pytestmark = pytest.mark.integration

INTEGRATION_COLLECTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000088")
ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def engine():
    eng = create_async_engine(settings.DATABASE_URL, pool_size=2)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="module")
async def db(engine):
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_collection(engine):
    """Create a test collection and seed three documents."""
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    docs_data = [
        {
            "external_id": "integ_billing",
            "title": "How to Pay Your Bill",
            "content": (
                "Pay your Ooredoo bill online through the My Ooredoo app, "
                "bank cards, or at retail stores. Bills are generated monthly. "
                "Late fees apply after 15 days."
            ),
        },
        {
            "external_id": "integ_5g",
            "title": "5G Network Plans",
            "content": (
                "Ooredoo 5G plans start at 2000 DA per month with 50GB data. "
                "Coverage includes Algiers, Oran, and Constantine. Enterprise "
                "packages available with SLA guarantees."
            ),
        },
        {
            "external_id": "integ_sim",
            "title": "SIM Replacement Guide",
            "content": (
                "Lost your SIM card? Visit any Ooredoo store with your ID "
                "to get a replacement for 200 DA. eSIM available for compatible "
                "devices. Activation takes 2 hours."
            ),
        },
    ]

    async with factory() as db:
        # Cleanup
        await db.execute(
            text("DELETE FROM collections WHERE id = :cid"),
            {"cid": str(INTEGRATION_COLLECTION_ID)},
        )
        await db.commit()

        # Create collection
        collection = Collection(
            id=INTEGRATION_COLLECTION_ID,
            org_id=ORG_ID,
            name="integration_test",
            embedding_model="bge-m3",
            embedding_dim=1024,
        )
        db.add(collection)
        await db.flush()

        # Ingest documents through the full pipeline
        for doc_data in docs_data:
            doc = Document(
                collection_id=INTEGRATION_COLLECTION_ID,
                external_id=doc_data["external_id"],
                title=doc_data["title"],
                content=doc_data["content"],
                status="indexed",
            )
            db.add(doc)
            await db.flush()

            chunks = chunk_text(doc_data["content"], strategy="adaptive")
            chunk_texts = []
            chunk_models = []
            for cr in chunks:
                cm = Chunk(
                    document_id=doc.id,
                    collection_id=INTEGRATION_COLLECTION_ID,
                    chunk_index=cr.chunk_index,
                    content=cr.content,
                    token_count=cr.token_count,
                    char_start=cr.char_start,
                    char_end=cr.char_end,
                )
                db.add(cm)
                chunk_models.append(cm)
                chunk_texts.append(cr.content)

            await db.flush()

            vectors = compute_embeddings(chunk_texts)
            for cm, vec in zip(chunk_models, vectors):
                db.add(Embedding(
                    chunk_id=cm.id,
                    collection_id=INTEGRATION_COLLECTION_ID,
                    vector=vec,
                    model_version="bge-m3",
                ))

        await db.commit()

    yield

    async with factory() as db:
        await db.execute(
            text("DELETE FROM collections WHERE id = :cid"),
            {"cid": str(INTEGRATION_COLLECTION_ID)},
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Semantic search tests
# ---------------------------------------------------------------------------

class TestSemanticPipeline:
    @pytest.mark.asyncio
    async def test_finds_billing_doc(self, db):
        """Semantic search for billing query returns the billing document."""
        query = "how to pay my mobile phone bill"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=5)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        ids = [r.external_id for r in response.results]
        assert "integ_billing" in ids, f"Billing doc not found. Got: {ids}"

    @pytest.mark.asyncio
    async def test_finds_5g_doc(self, db):
        query = "5G data plans pricing"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=5)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        ids = [r.external_id for r in response.results]
        assert "integ_5g" in ids

    @pytest.mark.asyncio
    async def test_finds_sim_doc_with_paraphrase(self, db):
        """Paraphrased query should still find the right document."""
        query = "I lost my phone chip need a new one"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=5)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        ids = [r.external_id for r in response.results]
        assert "integ_sim" in ids, f"SIM doc not found. Got: {ids}"

    @pytest.mark.asyncio
    async def test_ranking_order(self, db):
        """The most relevant document should rank first."""
        query = "SIM card replacement"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=5)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        assert len(response.results) > 0
        assert response.results[0].external_id == "integ_sim"

    @pytest.mark.asyncio
    async def test_scores_are_valid(self, db):
        query = "mobile internet"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=5)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        for r in response.results:
            assert 0.0 <= r.score <= 1.0, f"Invalid score: {r.score}"

    @pytest.mark.asyncio
    async def test_scores_are_descending(self, db):
        query = "Ooredoo services"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=10)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        scores = [r.score for r in response.results]
        assert scores == sorted(scores, reverse=True), "Scores not descending"


# ---------------------------------------------------------------------------
# Keyword search tests
# ---------------------------------------------------------------------------

class TestKeywordPipeline:
    @pytest.mark.asyncio
    async def test_keyword_exact_match(self, db):
        query = "eSIM activation"
        request = SearchRequest(query=query, mode="keyword", limit=5)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request
        )
        ids = [r.external_id for r in response.results]
        assert "integ_sim" in ids

    @pytest.mark.asyncio
    async def test_keyword_no_results_for_absent_term(self, db):
        query = "xylophone quantum blockchain"
        request = SearchRequest(query=query, mode="keyword", limit=5)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request
        )
        assert len(response.results) == 0


# ---------------------------------------------------------------------------
# Hybrid search tests
# ---------------------------------------------------------------------------

class TestHybridPipeline:
    @pytest.mark.asyncio
    async def test_hybrid_returns_results(self, db):
        query = "pay bill online"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="hybrid", limit=5)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        assert len(response.results) > 0
        ids = [r.external_id for r in response.results]
        assert "integ_billing" in ids

    @pytest.mark.asyncio
    async def test_hybrid_boosts_dual_match(self, db):
        """A document matching both semantic AND keyword should rank higher."""
        query = "5G plans 2000 DA"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="hybrid", limit=5)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        # 5G doc has both keyword AND semantic match — should rank first
        if response.results:
            assert response.results[0].external_id == "integ_5g"


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestResponseStructure:
    @pytest.mark.asyncio
    async def test_response_has_query_id(self, db):
        query = "test"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=1)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        assert response.query_id is not None

    @pytest.mark.asyncio
    async def test_response_has_latency(self, db):
        query = "test"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=1)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        assert response.took_ms >= 0

    @pytest.mark.asyncio
    async def test_highlights_generated(self, db):
        query = "bill payment"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=5, highlight=True)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        # At least one result should have highlights
        has_highlights = any(r.highlights for r in response.results)
        assert has_highlights, "No highlights generated"

    @pytest.mark.asyncio
    async def test_min_score_filter(self, db):
        query = "Ooredoo"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(
            query=query, mode="semantic", limit=10, min_score=0.5
        )
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        for r in response.results:
            assert r.score >= 0.5, f"Score {r.score} below min_score"

    @pytest.mark.asyncio
    async def test_limit_respected(self, db):
        query = "Ooredoo"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=1)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        assert len(response.results) <= 1

    @pytest.mark.asyncio
    async def test_total_count(self, db):
        query = "Ooredoo"
        vec = compute_embeddings([query])[0]
        request = SearchRequest(query=query, mode="semantic", limit=1)
        response = await execute_search(
            db, INTEGRATION_COLLECTION_ID, request, vec
        )
        assert response.total >= len(response.results)
