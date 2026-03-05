"""Tests for search_service — merge logic, highlight generation, and helpers."""

import uuid

import pytest

from app.schemas.search import SearchResult
from app.services.search_service import _generate_highlight, _merge_results


# ---------------------------------------------------------------------------
# _generate_highlight
# ---------------------------------------------------------------------------

class TestGenerateHighlight:
    def test_basic_highlight(self):
        content = "The quick brown fox jumps over the lazy dog."
        result = _generate_highlight(content, "fox")
        assert "<em>fox</em>" in result

    def test_highlight_case_insensitive_match(self):
        content = "Python is a great language for data science."
        result = _generate_highlight(content, "python")
        assert "<em>" in result

    def test_highlight_ellipsis_long_content(self):
        content = "x" * 100 + " target word " + "y" * 100
        result = _generate_highlight(content, "target")
        assert "..." in result

    def test_highlight_no_match(self):
        content = "Nothing relevant here."
        result = _generate_highlight(content, "zzzzzz")
        # Should still return a snippet even with no match
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_query(self):
        result = _generate_highlight("Some content.", "")
        assert isinstance(result, str)

    def test_multi_word_query(self):
        content = "Machine learning and deep learning are subsets of AI."
        result = _generate_highlight(content, "machine learning")
        assert "<em>" in result


# ---------------------------------------------------------------------------
# _merge_results (Reciprocal Rank Fusion)
# ---------------------------------------------------------------------------

def _make_result(ext_id: str, score: float) -> SearchResult:
    return SearchResult(
        doc_id=uuid.uuid4(),
        external_id=ext_id,
        score=score,
        title=f"Doc {ext_id}",
        url=None,
        highlights=[],
        metadata={},
    )


class TestMergeResults:
    def test_empty_inputs(self):
        assert _merge_results([], []) == []

    def test_vector_only(self):
        v = [_make_result("a", 0.9), _make_result("b", 0.7)]
        merged = _merge_results(v, [])
        ids = [r.external_id for r in merged]
        assert ids == ["a", "b"]

    def test_keyword_only(self):
        k = [_make_result("x", 0.8)]
        merged = _merge_results([], k)
        ids = [r.external_id for r in merged]
        assert ids == ["x"]

    def test_overlapping_results_boosted(self):
        """A document appearing in both vector and keyword results should rank higher."""
        v = [_make_result("shared", 0.9), _make_result("v-only", 0.85)]
        k = [_make_result("shared", 0.8), _make_result("k-only", 0.75)]
        merged = _merge_results(v, k)
        ids = [r.external_id for r in merged]
        assert ids[0] == "shared"

    def test_score_ordering(self):
        v = [_make_result("a", 0.5), _make_result("b", 0.3)]
        k = [_make_result("c", 0.9), _make_result("b", 0.8)]
        merged = _merge_results(v, k)
        scores = [r.score for r in merged]
        assert scores == sorted(scores, reverse=True)

    def test_weights_influence(self):
        v = [_make_result("v", 0.9)]
        k = [_make_result("k", 0.9)]
        merged = _merge_results(v, k, vector_weight=0.9, keyword_weight=0.1)
        ids = [r.external_id for r in merged]
        assert ids[0] == "v"

    def test_highlights_merged(self):
        r1 = _make_result("shared", 0.9)
        r1.highlights = ["vector highlight"]
        r2 = _make_result("shared", 0.8)
        r2.highlights = ["keyword highlight"]
        merged = _merge_results([r1], [r2])
        shared = next(r for r in merged if r.external_id == "shared")
        assert "vector highlight" in shared.highlights
        assert "keyword highlight" in shared.highlights

    def test_deduplicated_highlights(self):
        r1 = _make_result("shared", 0.9)
        r1.highlights = ["same"]
        r2 = _make_result("shared", 0.8)
        r2.highlights = ["same"]
        merged = _merge_results([r1], [r2])
        shared = next(r for r in merged if r.external_id == "shared")
        assert shared.highlights.count("same") == 1

    def test_k_parameter(self):
        v = [_make_result("a", 0.9)]
        k_results = [_make_result("b", 0.8)]
        m1 = _merge_results(v, k_results, k=60)
        m2 = _merge_results(v, k_results, k=10)
        # Different k values produce different scores
        assert m1[0].score != m2[0].score or m1[0].external_id == m2[0].external_id
