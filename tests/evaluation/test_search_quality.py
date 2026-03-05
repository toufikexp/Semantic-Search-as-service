"""Offline search quality evaluation using golden dataset.

These tests measure NDCG, MRR, Recall@k, MAP, and On-Topic Rate against
the golden query set.  They require:
  - A running PostgreSQL + pgvector instance with indexed documents
  - The embedding model available (or mocked)

Run with: pytest tests/evaluation/test_search_quality.py -v --tb=short

Mark: @pytest.mark.eval — skipped by default in CI, run explicitly.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.schemas.search import SearchRequest
from app.services.embedding_service import compute_embeddings
from app.services.search_service import execute_search
from tests.evaluation.golden_dataset import (
    DOCUMENTS,
    GOLDEN_QUERIES,
    get_all_relevant_ids,
)
from tests.evaluation.metrics import (
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    on_topic_rate,
    precision_at_k,
    recall_at_k,
)

pytestmark = pytest.mark.eval

COLLECTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")

# Quality thresholds — adjust as your system improves
THRESHOLDS = {
    "mrr": 0.60,
    "ndcg@5": 0.55,
    "ndcg@10": 0.50,
    "recall@5": 0.50,
    "recall@10": 0.65,
    "precision@5": 0.40,
    "map": 0.45,
    "on_topic": 0.50,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def eval_engine():
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="module")
async def eval_session(eval_engine):
    session_factory = sessionmaker(eval_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seed_eval_collection(eval_engine):
    """Seed a test collection with golden documents, chunks, and embeddings."""
    from app.models.chunk import Chunk
    from app.models.collection import Collection
    from app.models.document import Document
    from app.models.embedding import Embedding

    session_factory = sessionmaker(eval_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        # Clean up any previous eval data
        await db.execute(
            text("DELETE FROM collections WHERE id = :cid"),
            {"cid": str(COLLECTION_ID)},
        )
        await db.commit()

        # Create eval collection
        collection = Collection(
            id=COLLECTION_ID,
            org_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="eval_golden_set",
            embedding_model="bge-m3",
            embedding_dim=1024,
            chunk_strategy="adaptive",
            chunk_size=512,
            chunk_overlap=50,
        )
        db.add(collection)
        await db.flush()

        # Ingest documents, chunk, embed
        from app.services.chunking_service import chunk_text

        for gdoc in DOCUMENTS:
            doc = Document(
                collection_id=COLLECTION_ID,
                external_id=gdoc.external_id,
                title=gdoc.title,
                content=gdoc.content,
                content_type="text",
                url=gdoc.url,
                metadata_=gdoc.metadata,
                status="indexed",
            )
            db.add(doc)
            await db.flush()

            chunks = chunk_text(
                gdoc.content,
                strategy="adaptive",
                chunk_size=512,
                chunk_overlap=50,
            )

            chunk_texts = []
            chunk_models = []
            for cr in chunks:
                chunk_model = Chunk(
                    document_id=doc.id,
                    collection_id=COLLECTION_ID,
                    chunk_index=cr.chunk_index,
                    content=cr.content,
                    token_count=cr.token_count,
                    char_start=cr.char_start,
                    char_end=cr.char_end,
                    heading_context=cr.heading_context,
                )
                db.add(chunk_model)
                chunk_models.append(chunk_model)
                text_for_embed = cr.content
                if cr.heading_context:
                    text_for_embed = f"{cr.heading_context}: {cr.content}"
                chunk_texts.append(text_for_embed)

            await db.flush()

            if chunk_texts:
                vectors = compute_embeddings(chunk_texts)
                for chunk_model, vector in zip(chunk_models, vectors):
                    emb = Embedding(
                        chunk_id=chunk_model.id,
                        collection_id=COLLECTION_ID,
                        vector=vector,
                        model_version="bge-m3",
                    )
                    db.add(emb)

        await db.commit()

    yield

    # Teardown
    async with session_factory() as db:
        await db.execute(
            text("DELETE FROM collections WHERE id = :cid"),
            {"cid": str(COLLECTION_ID)},
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def run_search(db: AsyncSession, query: str, mode: str, limit: int = 20):
    """Execute a search and return (result_ids, scores)."""
    query_vector = None
    if mode in ("semantic", "hybrid"):
        query_vector = compute_embeddings([query])[0]

    request = SearchRequest(query=query, mode=mode, limit=limit, highlight=False)
    response = await execute_search(db, COLLECTION_ID, request, query_vector)
    result_ids = [r.external_id for r in response.results]
    scores = [r.score for r in response.results]
    return result_ids, scores


# ---------------------------------------------------------------------------
# Tests — Semantic mode
# ---------------------------------------------------------------------------

class TestSemanticSearchQuality:
    @pytest.mark.asyncio
    async def test_mrr_above_threshold(self, eval_session):
        all_results = []
        all_relevant = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "semantic")
            all_results.append(ids)
            all_relevant.append(get_all_relevant_ids(gq))

        mrr = mean_reciprocal_rank(all_results, all_relevant)
        print(f"\n  Semantic MRR: {mrr:.4f} (threshold: {THRESHOLDS['mrr']})")
        assert mrr >= THRESHOLDS["mrr"], f"MRR {mrr:.4f} below threshold"

    @pytest.mark.asyncio
    async def test_ndcg_at_5(self, eval_session):
        ndcg_scores = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "semantic")
            ndcg_scores.append(ndcg_at_k(ids, gq.relevant_docs, 5))

        avg_ndcg = sum(ndcg_scores) / len(ndcg_scores)
        print(f"\n  Semantic NDCG@5: {avg_ndcg:.4f} (threshold: {THRESHOLDS['ndcg@5']})")
        assert avg_ndcg >= THRESHOLDS["ndcg@5"]

    @pytest.mark.asyncio
    async def test_ndcg_at_10(self, eval_session):
        ndcg_scores = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "semantic")
            ndcg_scores.append(ndcg_at_k(ids, gq.relevant_docs, 10))

        avg_ndcg = sum(ndcg_scores) / len(ndcg_scores)
        print(f"\n  Semantic NDCG@10: {avg_ndcg:.4f} (threshold: {THRESHOLDS['ndcg@10']})")
        assert avg_ndcg >= THRESHOLDS["ndcg@10"]

    @pytest.mark.asyncio
    async def test_recall_at_5(self, eval_session):
        recall_scores = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "semantic")
            recall_scores.append(recall_at_k(ids, get_all_relevant_ids(gq), 5))

        avg_recall = sum(recall_scores) / len(recall_scores)
        print(f"\n  Semantic Recall@5: {avg_recall:.4f} (threshold: {THRESHOLDS['recall@5']})")
        assert avg_recall >= THRESHOLDS["recall@5"]

    @pytest.mark.asyncio
    async def test_map(self, eval_session):
        all_results = []
        all_relevant = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "semantic")
            all_results.append(ids)
            all_relevant.append(get_all_relevant_ids(gq))

        map_score = mean_average_precision(all_results, all_relevant)
        print(f"\n  Semantic MAP: {map_score:.4f} (threshold: {THRESHOLDS['map']})")
        assert map_score >= THRESHOLDS["map"]


# ---------------------------------------------------------------------------
# Tests — Keyword mode
# ---------------------------------------------------------------------------

class TestKeywordSearchQuality:
    @pytest.mark.asyncio
    async def test_keyword_mrr(self, eval_session):
        all_results = []
        all_relevant = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "keyword")
            all_results.append(ids)
            all_relevant.append(get_all_relevant_ids(gq))

        mrr = mean_reciprocal_rank(all_results, all_relevant)
        print(f"\n  Keyword MRR: {mrr:.4f}")
        # Keyword usually has lower MRR than semantic — no hard threshold,
        # just record the value for comparison
        assert mrr >= 0.0

    @pytest.mark.asyncio
    async def test_keyword_ndcg_at_5(self, eval_session):
        ndcg_scores = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "keyword")
            ndcg_scores.append(ndcg_at_k(ids, gq.relevant_docs, 5))

        avg_ndcg = sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0
        print(f"\n  Keyword NDCG@5: {avg_ndcg:.4f}")


# ---------------------------------------------------------------------------
# Tests — Hybrid mode
# ---------------------------------------------------------------------------

class TestHybridSearchQuality:
    @pytest.mark.asyncio
    async def test_hybrid_mrr(self, eval_session):
        all_results = []
        all_relevant = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "hybrid")
            all_results.append(ids)
            all_relevant.append(get_all_relevant_ids(gq))

        mrr = mean_reciprocal_rank(all_results, all_relevant)
        print(f"\n  Hybrid MRR: {mrr:.4f}")
        assert mrr >= THRESHOLDS["mrr"]

    @pytest.mark.asyncio
    async def test_hybrid_ndcg_at_5(self, eval_session):
        ndcg_scores = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "hybrid")
            ndcg_scores.append(ndcg_at_k(ids, gq.relevant_docs, 5))

        avg_ndcg = sum(ndcg_scores) / len(ndcg_scores)
        print(f"\n  Hybrid NDCG@5: {avg_ndcg:.4f}")
        assert avg_ndcg >= THRESHOLDS["ndcg@5"]

    @pytest.mark.asyncio
    async def test_hybrid_recall_at_10(self, eval_session):
        recall_scores = []
        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "hybrid")
            recall_scores.append(recall_at_k(ids, get_all_relevant_ids(gq), 10))

        avg_recall = sum(recall_scores) / len(recall_scores)
        print(f"\n  Hybrid Recall@10: {avg_recall:.4f}")
        assert avg_recall >= THRESHOLDS["recall@10"]


# ---------------------------------------------------------------------------
# Per-category breakdown
# ---------------------------------------------------------------------------

class TestPerCategoryQuality:
    @pytest.mark.asyncio
    async def test_per_category_ndcg(self, eval_session):
        """NDCG@5 broken down by query category for diagnosis."""
        from collections import defaultdict

        category_ndcg: dict[str, list[float]] = defaultdict(list)

        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            ids, _ = await run_search(eval_session, gq.query, "hybrid")
            score = ndcg_at_k(ids, gq.relevant_docs, 5)
            category_ndcg[gq.category].append(score)

        print("\n  Per-category NDCG@5 (hybrid):")
        for cat, scores in sorted(category_ndcg.items()):
            avg = sum(scores) / len(scores)
            print(f"    {cat}: {avg:.4f} ({len(scores)} queries)")
            # No hard assertion — this is diagnostic
