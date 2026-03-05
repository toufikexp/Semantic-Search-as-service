"""Unit tests for the IR metrics library.

These tests verify correctness of the metric calculations against
hand-computed expected values. They do NOT require a database or model.
"""

import math

import pytest

from tests.evaluation.metrics import (
    average_precision,
    dcg_at_k,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    on_topic_rate,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    score_gap,
    top_bottom_ratio,
)


# ── Precision@k ─────────────────────────────────────────────────────────

class TestPrecisionAtK:
    def test_perfect_precision(self):
        results = ["a", "b", "c"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(results, relevant, 3) == 1.0

    def test_no_relevant(self):
        results = ["x", "y", "z"]
        relevant = {"a", "b"}
        assert precision_at_k(results, relevant, 3) == 0.0

    def test_partial_match(self):
        results = ["a", "x", "b", "y", "c"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(results, relevant, 4) == 0.5  # 2 out of 4

    def test_k_larger_than_results(self):
        results = ["a"]
        relevant = {"a"}
        assert precision_at_k(results, relevant, 5) == pytest.approx(0.2)

    def test_k_zero(self):
        assert precision_at_k(["a"], {"a"}, 0) == 0.0

    def test_empty_results(self):
        assert precision_at_k([], {"a"}, 5) == 0.0


# ── Recall@k ─────────────────────────────────────────────────────────────

class TestRecallAtK:
    def test_perfect_recall(self):
        results = ["a", "b", "c"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(results, relevant, 3) == 1.0

    def test_partial_recall(self):
        results = ["a", "x", "y"]
        relevant = {"a", "b"}
        assert recall_at_k(results, relevant, 3) == 0.5

    def test_no_recall(self):
        results = ["x", "y", "z"]
        relevant = {"a", "b"}
        assert recall_at_k(results, relevant, 3) == 0.0

    def test_empty_relevant_set(self):
        # Convention: if nothing is relevant, recall is 1.0
        assert recall_at_k(["a", "b"], set(), 2) == 1.0

    def test_k_one(self):
        results = ["b", "a"]
        relevant = {"a", "b"}
        assert recall_at_k(results, relevant, 1) == 0.5


# ── Reciprocal Rank ──────────────────────────────────────────────────────

class TestReciprocalRank:
    def test_first_position(self):
        assert reciprocal_rank(["a", "b"], {"a"}) == 1.0

    def test_second_position(self):
        assert reciprocal_rank(["x", "a"], {"a"}) == 0.5

    def test_third_position(self):
        assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)

    def test_not_found(self):
        assert reciprocal_rank(["x", "y"], {"a"}) == 0.0

    def test_multiple_relevant(self):
        # Only first relevant counts
        assert reciprocal_rank(["x", "a", "b"], {"a", "b"}) == 0.5


# ── MRR ──────────────────────────────────────────────────────────────────

class TestMRR:
    def test_perfect_mrr(self):
        all_results = [["a"], ["b"]]
        all_relevant = [{"a"}, {"b"}]
        assert mean_reciprocal_rank(all_results, all_relevant) == 1.0

    def test_mixed_mrr(self):
        all_results = [["a", "b"], ["x", "b"]]
        all_relevant = [{"a"}, {"b"}]
        # RR for q1 = 1.0, RR for q2 = 0.5 => MRR = 0.75
        assert mean_reciprocal_rank(all_results, all_relevant) == 0.75

    def test_empty(self):
        assert mean_reciprocal_rank([], []) == 0.0


# ── Average Precision ────────────────────────────────────────────────────

class TestAveragePrecision:
    def test_perfect_ap(self):
        results = ["a", "b", "c"]
        relevant = {"a", "b", "c"}
        # P@1=1, P@2=1, P@3=1 => AP = 1.0
        assert average_precision(results, relevant) == 1.0

    def test_interleaved(self):
        results = ["a", "x", "b"]
        relevant = {"a", "b"}
        # P@1=1/1, P@3=2/3 => AP = (1 + 2/3)/2 = 5/6
        assert average_precision(results, relevant) == pytest.approx(5 / 6)

    def test_all_irrelevant(self):
        assert average_precision(["x", "y"], {"a"}) == 0.0


# ── MAP ──────────────────────────────────────────────────────────────────

class TestMAP:
    def test_map_two_queries(self):
        all_results = [["a", "b"], ["x", "b"]]
        all_relevant = [{"a", "b"}, {"b"}]
        ap1 = average_precision(["a", "b"], {"a", "b"})
        ap2 = average_precision(["x", "b"], {"b"})
        expected = (ap1 + ap2) / 2
        assert mean_average_precision(all_results, all_relevant) == pytest.approx(
            expected
        )


# ── DCG / NDCG ───────────────────────────────────────────────────────────

class TestDCGAndNDCG:
    def test_dcg_known_values(self):
        # results: [3, 2, 1, 0] relevance grades
        results = ["a", "b", "c", "d"]
        relevance = {"a": 3, "b": 2, "c": 1, "d": 0}
        dcg = dcg_at_k(results, relevance, 4)
        # Hand-computed:
        #   (2^3-1)/log2(2) + (2^2-1)/log2(3) + (2^1-1)/log2(4) + 0
        #   = 7/1 + 3/1.585 + 1/2 + 0 = 7 + 1.893 + 0.5 = 9.393
        assert dcg == pytest.approx(9.3927, rel=1e-3)

    def test_ndcg_perfect_ranking(self):
        results = ["a", "b", "c"]
        relevance = {"a": 3, "b": 2, "c": 1}
        # Perfect ranking should give NDCG = 1.0
        assert ndcg_at_k(results, relevance, 3) == pytest.approx(1.0)

    def test_ndcg_reversed_ranking(self):
        results = ["c", "b", "a"]
        relevance = {"a": 3, "b": 2, "c": 1}
        ndcg = ndcg_at_k(results, relevance, 3)
        # Reversed ranking should be < 1.0
        assert 0.0 < ndcg < 1.0

    def test_ndcg_no_relevant(self):
        results = ["x", "y"]
        relevance = {"a": 3}
        assert ndcg_at_k(results, relevance, 2) == 0.0

    def test_ndcg_at_1(self):
        results = ["a", "b"]
        relevance = {"a": 3, "b": 1}
        # Only top result matters. a has max relevance => NDCG@1 = 1.0
        assert ndcg_at_k(results, relevance, 1) == pytest.approx(1.0)

    def test_ndcg_at_1_wrong_top(self):
        results = ["b", "a"]
        relevance = {"a": 3, "b": 1}
        ndcg = ndcg_at_k(results, relevance, 1)
        # b has rel=1, ideal is a with rel=3
        # actual DCG = (2^1-1)/log2(2) = 1.0
        # ideal DCG = (2^3-1)/log2(2) = 7.0
        assert ndcg == pytest.approx(1 / 7, rel=1e-3)

    def test_ndcg_empty_relevance(self):
        assert ndcg_at_k(["a", "b"], {}, 2) == 0.0


# ── On-topic Rate ────────────────────────────────────────────────────────

class TestOnTopicRate:
    def test_all_on_topic(self):
        results = ["a", "b"]
        relevant = {"a", "b"}
        assert on_topic_rate(results, relevant) == 1.0

    def test_none_on_topic(self):
        results = ["x", "y"]
        relevant = {"a"}
        assert on_topic_rate(results, relevant) == 0.0

    def test_half_on_topic(self):
        results = ["a", "x", "b", "y"]
        relevant = {"a", "b"}
        assert on_topic_rate(results, relevant) == 0.5

    def test_empty_results(self):
        assert on_topic_rate([], {"a"}) == 0.0


# ── Score Distribution ───────────────────────────────────────────────────

class TestScoreDistribution:
    def test_score_gap_uniform(self):
        # Uniform decay: 0.1 gap each
        scores = [1.0, 0.9, 0.8, 0.7]
        assert score_gap(scores) == pytest.approx(0.1, rel=1e-3)

    def test_score_gap_single(self):
        assert score_gap([0.9]) == 0.0

    def test_top_bottom_ratio(self):
        scores = [0.9, 0.85, 0.8, 0.3, 0.2, 0.1]
        ratio = top_bottom_ratio(scores, top_n=3)
        top_avg = (0.9 + 0.85 + 0.8) / 3
        bot_avg = (0.3 + 0.2 + 0.1) / 3
        assert ratio == pytest.approx(top_avg / bot_avg, rel=1e-3)

    def test_top_bottom_not_enough_scores(self):
        assert top_bottom_ratio([0.5, 0.4], top_n=3) == 0.0
