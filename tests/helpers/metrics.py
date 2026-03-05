"""Search quality metrics: NDCG, MRR, Recall@k, Precision@k, On-Topic Rate.

All functions accept a ranked list of result external_ids and a relevance
dict mapping external_id -> graded relevance (0-3).
"""

import math


def ndcg_at_k(
    ranked_ids: list[str],
    relevance: dict[str, int],
    k: int = 10,
) -> float:
    """Normalized Discounted Cumulative Gain at rank k.

    Measures ranking quality, penalizing relevant results that appear lower.
    """
    dcg = _dcg(ranked_ids[:k], relevance)
    ideal_ranking = sorted(relevance.keys(), key=lambda x: relevance[x], reverse=True)
    idcg = _dcg(ideal_ranking[:k], relevance)
    if idcg == 0:
        return 0.0
    return dcg / idcg


def _dcg(ranked_ids: list[str], relevance: dict[str, int]) -> float:
    total = 0.0
    for i, doc_id in enumerate(ranked_ids):
        rel = relevance.get(doc_id, 0)
        total += (2**rel - 1) / math.log2(i + 2)
    return total


def mrr(ranked_ids: list[str], relevance: dict[str, int]) -> float:
    """Mean Reciprocal Rank — reciprocal of the rank of the first relevant result."""
    for i, doc_id in enumerate(ranked_ids):
        if relevance.get(doc_id, 0) > 0:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(
    ranked_ids: list[str],
    relevance: dict[str, int],
    k: int = 10,
) -> float:
    """Fraction of relevant documents found in the top-k results."""
    relevant_set = {doc_id for doc_id, rel in relevance.items() if rel > 0}
    if not relevant_set:
        return 1.0
    found = sum(1 for doc_id in ranked_ids[:k] if doc_id in relevant_set)
    return found / len(relevant_set)


def precision_at_k(
    ranked_ids: list[str],
    relevance: dict[str, int],
    k: int = 10,
) -> float:
    """Fraction of top-k results that are relevant."""
    top_k = ranked_ids[:k]
    if not top_k:
        return 0.0
    relevant_count = sum(1 for doc_id in top_k if relevance.get(doc_id, 0) > 0)
    return relevant_count / len(top_k)


def on_topic_rate(
    ranked_ids: list[str],
    relevance: dict[str, int],
) -> float:
    """Percentage of returned results that have any relevance (score > 0)."""
    if not ranked_ids:
        return 0.0
    on_topic = sum(1 for doc_id in ranked_ids if relevance.get(doc_id, 0) > 0)
    return on_topic / len(ranked_ids)


def average_score(scores: list[float]) -> float:
    """Compute the arithmetic mean of a list of metric scores."""
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
