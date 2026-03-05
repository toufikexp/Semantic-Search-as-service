"""Search quality evaluation using the golden dataset and RRF merge logic.

These tests simulate search results from the golden corpus and verify that
the ranking metrics (NDCG, MRR, Recall@k) meet minimum quality thresholds.
They test the _merge_results function which is the core ranking algorithm
that doesn't require database or embedding infrastructure.

Mark: @pytest.mark.eval
"""

import uuid

import pytest

from app.schemas.search import SearchResult
from app.services.search_service import _merge_results
from tests.helpers.golden_data import EVALUATION_QUERIES, GOLDEN_DOCUMENTS, make_doc_id_map
from tests.helpers.metrics import (
    average_score,
    mrr,
    ndcg_at_k,
    on_topic_rate,
    recall_at_k,
)


DOC_IDS = make_doc_id_map()


def _simulate_vector_results(
    query_info: dict, noise_factor: float = 0.05
) -> list[SearchResult]:
    """Simulate vector search results ordered by relevance with small noise."""
    relevance = query_info["relevance"]
    sorted_docs = sorted(relevance.items(), key=lambda x: x[1], reverse=True)
    results = []
    for ext_id, rel in sorted_docs:
        score = 0.3 * rel + 0.1 - noise_factor * len(results)
        results.append(
            SearchResult(
                doc_id=DOC_IDS.get(ext_id, uuid.uuid4()),
                external_id=ext_id,
                score=max(score, 0.01),
                title=ext_id,
                url=None,
                highlights=[],
                metadata={},
            )
        )
    return results


def _simulate_keyword_results(query_info: dict) -> list[SearchResult]:
    """Simulate keyword results — biased toward exact term matches."""
    relevance = query_info["relevance"]
    sorted_docs = sorted(relevance.items(), key=lambda x: x[1], reverse=True)
    results = []
    for ext_id, rel in sorted_docs:
        score = 0.2 * rel
        results.append(
            SearchResult(
                doc_id=DOC_IDS.get(ext_id, uuid.uuid4()),
                external_id=ext_id,
                score=max(score, 0.01),
                title=ext_id,
                url=None,
                highlights=[],
                metadata={},
            )
        )
    return results


@pytest.mark.eval
class TestHybridSearchQuality:
    """Evaluate the RRF merge algorithm against golden queries."""

    def _run_query(self, query_info: dict) -> list[str]:
        vector = _simulate_vector_results(query_info)
        keyword = _simulate_keyword_results(query_info)
        merged = _merge_results(vector, keyword, vector_weight=0.7, keyword_weight=0.3, k=60)
        return [r.external_id for r in merged]

    def test_ndcg_per_query(self):
        scores = []
        for q in EVALUATION_QUERIES:
            ranked = self._run_query(q)
            score = ndcg_at_k(ranked, q["relevance"], k=5)
            scores.append(score)
            # Each individual query should have reasonable ranking
            assert score > 0.3, f"NDCG too low for query: {q['query']}"
        avg = average_score(scores)
        assert avg > 0.5, f"Average NDCG@5 = {avg:.3f}, expected > 0.5"

    def test_mrr_per_query(self):
        scores = []
        for q in EVALUATION_QUERIES:
            ranked = self._run_query(q)
            score = mrr(ranked, q["relevance"])
            scores.append(score)
            assert score > 0.0, f"MRR=0 for query: {q['query']}"
        avg = average_score(scores)
        assert avg > 0.7, f"Average MRR = {avg:.3f}, expected > 0.7"

    def test_recall_at_5(self):
        scores = []
        for q in EVALUATION_QUERIES:
            ranked = self._run_query(q)
            score = recall_at_k(ranked, q["relevance"], k=5)
            scores.append(score)
        avg = average_score(scores)
        assert avg > 0.6, f"Average Recall@5 = {avg:.3f}, expected > 0.6"

    def test_on_topic_rate(self):
        rates = []
        for q in EVALUATION_QUERIES:
            ranked = self._run_query(q)
            rate = on_topic_rate(ranked, q["relevance"])
            rates.append(rate)
        avg = average_score(rates)
        assert avg > 0.5, f"Average On-Topic Rate = {avg:.3f}, expected > 0.5"

    def test_top_result_is_most_relevant(self):
        """For each golden query, the top result should be the most relevant doc."""
        for q in EVALUATION_QUERIES:
            ranked = self._run_query(q)
            best_doc = max(q["relevance"], key=q["relevance"].get)
            assert ranked[0] == best_doc, (
                f"Top result for '{q['query']}' was {ranked[0]}, expected {best_doc}"
            )


@pytest.mark.eval
class TestVectorWeightImpact:
    """Verify that adjusting vector vs keyword weight changes rankings."""

    def test_higher_vector_weight_favors_vector_results(self):
        q = EVALUATION_QUERIES[0]
        vector = _simulate_vector_results(q)
        keyword = _simulate_keyword_results(q)

        merged_vector_heavy = _merge_results(vector, keyword, vector_weight=0.9, keyword_weight=0.1)
        merged_keyword_heavy = _merge_results(vector, keyword, vector_weight=0.1, keyword_weight=0.9)

        # Scores should differ
        scores_vh = [r.score for r in merged_vector_heavy]
        scores_kh = [r.score for r in merged_keyword_heavy]
        assert scores_vh != scores_kh


@pytest.mark.eval
class TestEdgeCaseQueries:
    """Evaluate merge behavior with edge-case inputs."""

    def test_single_result_from_each(self):
        vector = [
            SearchResult(
                doc_id=uuid.uuid4(), external_id="v1", score=0.9,
                title="V", url=None, highlights=[], metadata={},
            )
        ]
        keyword = [
            SearchResult(
                doc_id=uuid.uuid4(), external_id="k1", score=0.8,
                title="K", url=None, highlights=[], metadata={},
            )
        ]
        merged = _merge_results(vector, keyword)
        assert len(merged) == 2

    def test_all_same_score(self):
        results = [
            SearchResult(
                doc_id=uuid.uuid4(), external_id=f"d{i}", score=0.5,
                title=f"D{i}", url=None, highlights=[], metadata={},
            )
            for i in range(5)
        ]
        merged = _merge_results(results, [])
        assert len(merged) == 5
