"""Information Retrieval metrics for evaluating search quality.

All functions take a ``results`` list (ranked document IDs from the system)
and a ``relevance`` dict mapping document IDs to graded relevance scores
(0 = irrelevant, 1 = marginally relevant, 2 = relevant, 3 = highly relevant).
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Core IR Metrics
# ---------------------------------------------------------------------------


def precision_at_k(results: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the top-k results that are relevant (binary)."""
    if k <= 0:
        return 0.0
    top_k = results[:k]
    hits = sum(1 for doc in top_k if doc in relevant)
    return hits / k


def recall_at_k(results: list[str], relevant: set[str], k: int) -> float:
    """Fraction of all relevant documents found in the top-k results."""
    if not relevant:
        return 1.0
    top_k = results[:k]
    hits = sum(1 for doc in top_k if doc in relevant)
    return hits / len(relevant)


def average_precision(results: list[str], relevant: set[str]) -> float:
    """Average precision across all recall levels for a single query."""
    if not relevant:
        return 1.0
    hits = 0
    ap_sum = 0.0
    for rank, doc in enumerate(results, start=1):
        if doc in relevant:
            hits += 1
            ap_sum += hits / rank
    return ap_sum / len(relevant)


def mean_average_precision(
    all_results: list[list[str]], all_relevant: list[set[str]]
) -> float:
    """MAP across multiple queries."""
    if not all_results:
        return 0.0
    return sum(
        average_precision(r, rel) for r, rel in zip(all_results, all_relevant)
    ) / len(all_results)


def reciprocal_rank(results: list[str], relevant: set[str]) -> float:
    """Reciprocal of the rank of the first relevant document (MRR component)."""
    for rank, doc in enumerate(results, start=1):
        if doc in relevant:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(
    all_results: list[list[str]], all_relevant: list[set[str]]
) -> float:
    """MRR across multiple queries."""
    if not all_results:
        return 0.0
    return sum(
        reciprocal_rank(r, rel) for r, rel in zip(all_results, all_relevant)
    ) / len(all_results)


def dcg_at_k(results: list[str], relevance: dict[str, int], k: int) -> float:
    """Discounted Cumulative Gain at position k using graded relevance."""
    dcg = 0.0
    for i, doc in enumerate(results[:k]):
        rel = relevance.get(doc, 0)
        dcg += (2**rel - 1) / math.log2(i + 2)  # i+2 because log2(1)=0
    return dcg


def ndcg_at_k(results: list[str], relevance: dict[str, int], k: int) -> float:
    """Normalized Discounted Cumulative Gain at k.

    Compares actual DCG against ideal DCG (results sorted by true relevance).
    Returns a value in [0, 1] where 1.0 means perfect ranking.
    """
    actual = dcg_at_k(results, relevance, k)
    # Ideal ranking: sort all judged docs by relevance descending
    ideal_order = sorted(relevance.keys(), key=lambda d: relevance[d], reverse=True)
    ideal = dcg_at_k(ideal_order, relevance, k)
    if ideal == 0:
        return 0.0
    return actual / ideal


# ---------------------------------------------------------------------------
# On-topic / Relevance Rate
# ---------------------------------------------------------------------------


def on_topic_rate(results: list[str], relevant: set[str]) -> float:
    """Fraction of returned results that are relevant (at any grade)."""
    if not results:
        return 0.0
    return sum(1 for doc in results if doc in relevant) / len(results)


# ---------------------------------------------------------------------------
# Score Distribution Analysis
# ---------------------------------------------------------------------------


def score_gap(scores: list[float]) -> float:
    """Average gap between consecutive result scores.

    A healthy search system shows a gradual decay.  A large gap may indicate
    that top results are significantly better (good) or that scores are not
    well calibrated.
    """
    if len(scores) < 2:
        return 0.0
    gaps = [scores[i] - scores[i + 1] for i in range(len(scores) - 1)]
    return sum(gaps) / len(gaps)


def top_bottom_ratio(scores: list[float], top_n: int = 3) -> float:
    """Ratio of average top-N scores to average bottom-N scores.

    High ratio = clear differentiation between best and worst results.
    """
    if len(scores) < top_n * 2:
        return 0.0
    top_avg = sum(scores[:top_n]) / top_n
    bottom_avg = sum(scores[-top_n:]) / top_n
    if bottom_avg == 0:
        return float("inf")
    return top_avg / bottom_avg
