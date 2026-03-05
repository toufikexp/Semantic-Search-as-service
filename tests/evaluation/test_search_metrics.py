"""Unit tests for search quality metrics (NDCG, MRR, Recall@k, Precision@k).

These tests validate the metric computation functions themselves using
synthetic ranked lists. They do NOT require a database or embedding model.
"""

import pytest

from tests.helpers.metrics import (
    average_score,
    mrr,
    ndcg_at_k,
    on_topic_rate,
    precision_at_k,
    recall_at_k,
)


# ---------------------------------------------------------------------------
# NDCG
# ---------------------------------------------------------------------------

class TestNDCG:
    def test_perfect_ranking(self):
        relevance = {"a": 3, "b": 2, "c": 1}
        ranked = ["a", "b", "c"]
        score = ndcg_at_k(ranked, relevance, k=3)
        assert score == pytest.approx(1.0)

    def test_reversed_ranking(self):
        relevance = {"a": 3, "b": 2, "c": 1}
        ranked = ["c", "b", "a"]
        score = ndcg_at_k(ranked, relevance, k=3)
        assert 0.0 < score < 1.0

    def test_no_relevant_results(self):
        relevance = {"a": 3}
        ranked = ["x", "y", "z"]
        score = ndcg_at_k(ranked, relevance, k=3)
        assert score == pytest.approx(0.0)

    def test_empty_results(self):
        relevance = {"a": 3}
        assert ndcg_at_k([], relevance, k=5) == pytest.approx(0.0)

    def test_empty_relevance(self):
        assert ndcg_at_k(["a", "b"], {}, k=5) == 0.0

    def test_k_limits_evaluation(self):
        relevance = {"a": 3, "b": 2, "c": 1}
        ranked = ["x", "a", "b", "c"]
        score_k1 = ndcg_at_k(ranked, relevance, k=1)
        score_k4 = ndcg_at_k(ranked, relevance, k=4)
        assert score_k1 == 0.0  # first result is irrelevant
        assert score_k4 > 0.0

    def test_single_result_perfect(self):
        relevance = {"a": 3}
        assert ndcg_at_k(["a"], relevance, k=1) == pytest.approx(1.0)

    def test_graded_relevance_matters(self):
        relevance = {"highly": 3, "somewhat": 1}
        rank_good = ["highly", "somewhat"]
        rank_bad = ["somewhat", "highly"]
        assert ndcg_at_k(rank_good, relevance, k=2) > ndcg_at_k(rank_bad, relevance, k=2)


# ---------------------------------------------------------------------------
# MRR
# ---------------------------------------------------------------------------

class TestMRR:
    def test_first_position(self):
        assert mrr(["a", "b"], {"a": 3}) == pytest.approx(1.0)

    def test_second_position(self):
        assert mrr(["x", "a"], {"a": 2}) == pytest.approx(0.5)

    def test_third_position(self):
        assert mrr(["x", "y", "a"], {"a": 1}) == pytest.approx(1 / 3)

    def test_no_relevant(self):
        assert mrr(["x", "y", "z"], {"a": 3}) == pytest.approx(0.0)

    def test_empty_results(self):
        assert mrr([], {"a": 3}) == pytest.approx(0.0)

    def test_zero_relevance_ignored(self):
        assert mrr(["a", "b"], {"a": 0, "b": 2}) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Recall@k
# ---------------------------------------------------------------------------

class TestRecallAtK:
    def test_perfect_recall(self):
        relevance = {"a": 3, "b": 2}
        assert recall_at_k(["a", "b", "c"], relevance, k=3) == pytest.approx(1.0)

    def test_partial_recall(self):
        relevance = {"a": 3, "b": 2, "c": 1}
        assert recall_at_k(["a", "x", "y"], relevance, k=3) == pytest.approx(1 / 3)

    def test_zero_recall(self):
        relevance = {"a": 3}
        assert recall_at_k(["x", "y"], relevance, k=2) == pytest.approx(0.0)

    def test_k_smaller_than_results(self):
        relevance = {"a": 3, "b": 2}
        assert recall_at_k(["a", "b"], relevance, k=1) == pytest.approx(0.5)

    def test_no_relevant_docs(self):
        assert recall_at_k(["a", "b"], {}, k=2) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Precision@k
# ---------------------------------------------------------------------------

class TestPrecisionAtK:
    def test_all_relevant(self):
        relevance = {"a": 3, "b": 2}
        assert precision_at_k(["a", "b"], relevance, k=2) == pytest.approx(1.0)

    def test_half_relevant(self):
        relevance = {"a": 3}
        assert precision_at_k(["a", "x"], relevance, k=2) == pytest.approx(0.5)

    def test_none_relevant(self):
        relevance = {"a": 3}
        assert precision_at_k(["x", "y"], relevance, k=2) == pytest.approx(0.0)

    def test_empty_results(self):
        assert precision_at_k([], {"a": 1}, k=5) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# On-Topic Rate
# ---------------------------------------------------------------------------

class TestOnTopicRate:
    def test_all_on_topic(self):
        relevance = {"a": 3, "b": 1}
        assert on_topic_rate(["a", "b"], relevance) == pytest.approx(1.0)

    def test_mixed(self):
        relevance = {"a": 3}
        assert on_topic_rate(["a", "x", "y"], relevance) == pytest.approx(1 / 3)

    def test_empty(self):
        assert on_topic_rate([], {"a": 1}) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Average helper
# ---------------------------------------------------------------------------

class TestAverageScore:
    def test_basic(self):
        assert average_score([1.0, 0.5, 0.0]) == pytest.approx(0.5)

    def test_empty(self):
        assert average_score([]) == pytest.approx(0.0)
