"""A/B comparison of search modes: semantic vs keyword vs hybrid.

This module runs the same golden queries across all three modes and compares
metrics side-by-side to validate that:
  1. Hybrid >= best of (semantic, keyword) on most metrics
  2. Semantic outperforms keyword on paraphrase/reformulation queries
  3. Keyword outperforms semantic on exact-match queries

These are diagnostic tests — they print comparison tables and only fail
if hybrid is significantly worse than both individual modes.

Run with: pytest tests/evaluation/test_mode_comparison.py -v -s
Mark: @pytest.mark.eval
"""

from __future__ import annotations

from collections import defaultdict

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.schemas.search import SearchRequest
from app.services.embedding_service import compute_embeddings
from app.services.search_service import execute_search
from tests.evaluation.golden_dataset import GOLDEN_QUERIES, get_all_relevant_ids
from tests.evaluation.metrics import (
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    recall_at_k,
)
from tests.evaluation.test_search_quality import COLLECTION_ID

pytestmark = pytest.mark.eval


@pytest_asyncio.fixture(scope="module")
async def eval_session():
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def search_mode(db: AsyncSession, query: str, mode: str):
    query_vector = None
    if mode in ("semantic", "hybrid"):
        query_vector = compute_embeddings([query])[0]
    request = SearchRequest(query=query, mode=mode, limit=20, highlight=False)
    response = await execute_search(db, COLLECTION_ID, request, query_vector)
    return [r.external_id for r in response.results]


# ---------------------------------------------------------------------------
# Mode comparison
# ---------------------------------------------------------------------------

class TestModeComparison:
    @pytest.mark.asyncio
    async def test_compare_all_modes(self, eval_session):
        """Run all golden queries through all three modes and compare."""
        modes = ["semantic", "keyword", "hybrid"]
        mode_results: dict[str, list[list[str]]] = defaultdict(list)
        all_relevant: list[set[str]] = []

        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue
            all_relevant.append(get_all_relevant_ids(gq))
            for mode in modes:
                ids = await search_mode(eval_session, gq.query, mode)
                mode_results[mode].append(ids)

        print("\n" + "=" * 70)
        print("  SEARCH MODE COMPARISON")
        print("=" * 70)
        print(f"  {'Metric':<20} {'Semantic':>10} {'Keyword':>10} {'Hybrid':>10}")
        print("-" * 70)

        metrics = {}
        for mode in modes:
            mrr = mean_reciprocal_rank(mode_results[mode], all_relevant)
            m_ap = mean_average_precision(mode_results[mode], all_relevant)

            ndcg5_scores = []
            ndcg10_scores = []
            recall5_scores = []
            recall10_scores = []

            for i, gq in enumerate(
                [q for q in GOLDEN_QUERIES if q.relevant_docs]
            ):
                ids = mode_results[mode][i]
                rel = get_all_relevant_ids(gq)
                ndcg5_scores.append(ndcg_at_k(ids, gq.relevant_docs, 5))
                ndcg10_scores.append(ndcg_at_k(ids, gq.relevant_docs, 10))
                recall5_scores.append(recall_at_k(ids, rel, 5))
                recall10_scores.append(recall_at_k(ids, rel, 10))

            metrics[mode] = {
                "MRR": mrr,
                "MAP": m_ap,
                "NDCG@5": sum(ndcg5_scores) / len(ndcg5_scores),
                "NDCG@10": sum(ndcg10_scores) / len(ndcg10_scores),
                "Recall@5": sum(recall5_scores) / len(recall5_scores),
                "Recall@10": sum(recall10_scores) / len(recall10_scores),
            }

        for metric_name in ["MRR", "MAP", "NDCG@5", "NDCG@10", "Recall@5", "Recall@10"]:
            vals = [metrics[m][metric_name] for m in modes]
            best_idx = vals.index(max(vals))
            row = f"  {metric_name:<20}"
            for i, v in enumerate(vals):
                marker = " *" if i == best_idx else "  "
                row += f"{v:>8.4f}{marker}"
            print(row)

        print("-" * 70)
        print("  (* = best mode for that metric)")
        print()

        # Hybrid should not be catastrophically worse than both
        for metric_name in ["MRR", "NDCG@5"]:
            hybrid_val = metrics["hybrid"][metric_name]
            sem_val = metrics["semantic"][metric_name]
            kw_val = metrics["keyword"][metric_name]
            best_single = max(sem_val, kw_val)
            # Allow 15% degradation from best single mode
            assert hybrid_val >= best_single * 0.85, (
                f"Hybrid {metric_name} ({hybrid_val:.4f}) is much worse than "
                f"best single mode ({best_single:.4f})"
            )


# ---------------------------------------------------------------------------
# Per-query mode winner analysis
# ---------------------------------------------------------------------------

class TestPerQueryModeAnalysis:
    @pytest.mark.asyncio
    async def test_which_mode_wins_per_query(self, eval_session):
        """For each query, show which mode performs best."""
        modes = ["semantic", "keyword", "hybrid"]
        wins = defaultdict(int)

        print("\n" + "=" * 70)
        print("  PER-QUERY MODE WINNER (by NDCG@5)")
        print("=" * 70)

        for gq in GOLDEN_QUERIES:
            if not gq.relevant_docs:
                continue

            best_mode = ""
            best_ndcg = -1.0

            for mode in modes:
                ids = await search_mode(eval_session, gq.query, mode)
                score = ndcg_at_k(ids, gq.relevant_docs, 5)
                if score > best_ndcg:
                    best_ndcg = score
                    best_mode = mode

            wins[best_mode] += 1
            print(f"  [{gq.category:>10}] {best_mode:>10} wins: {gq.query[:50]}")

        print()
        print("  Mode win counts:")
        for mode in modes:
            print(f"    {mode}: {wins[mode]}")
        print()


# ---------------------------------------------------------------------------
# Semantic vs Keyword on specific query types
# ---------------------------------------------------------------------------

class TestSemanticVsKeywordStrengths:
    @pytest.mark.asyncio
    async def test_semantic_wins_on_paraphrases(self, eval_session):
        """Semantic should outperform keyword on reformulated queries."""
        paraphrase_queries = [
            gq for gq in GOLDEN_QUERIES
            if gq.query in (
                "how much data do I get for 200 dinars",
                "I lost my SIM card what should I do",
                "configure internet settings on my phone",
            )
        ]
        assert len(paraphrase_queries) > 0

        sem_better_count = 0
        for gq in paraphrase_queries:
            sem_ids = await search_mode(eval_session, gq.query, "semantic")
            kw_ids = await search_mode(eval_session, gq.query, "keyword")
            sem_ndcg = ndcg_at_k(sem_ids, gq.relevant_docs, 5)
            kw_ndcg = ndcg_at_k(kw_ids, gq.relevant_docs, 5)
            if sem_ndcg >= kw_ndcg:
                sem_better_count += 1

        # Semantic should win on at least half of paraphrase queries
        assert sem_better_count >= len(paraphrase_queries) // 2, (
            f"Semantic only won {sem_better_count}/{len(paraphrase_queries)} "
            "paraphrase queries"
        )

    @pytest.mark.asyncio
    async def test_keyword_finds_exact_terms(self, eval_session):
        """Keyword should find documents with exact term matches."""
        exact_queries = [
            gq for gq in GOLDEN_QUERIES
            if gq.query in (
                "Ooredoo 5G offers and prices",
                "Ooredoo customer service phone number",
                "réclamation facture Ooredoo",
            )
        ]
        assert len(exact_queries) > 0

        for gq in exact_queries:
            kw_ids = await search_mode(eval_session, gq.query, "keyword")
            recall = recall_at_k(kw_ids, get_all_relevant_ids(gq), 5)
            # Keyword should find at least some relevant docs for exact queries
            assert recall > 0, f"Keyword found nothing for: {gq.query}"
