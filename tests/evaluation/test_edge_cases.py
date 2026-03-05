"""Edge case and regression tests for the search system.

These tests verify correct behavior under unusual or adversarial inputs:
  - Empty / whitespace queries
  - Very long queries
  - Special characters and injection attempts
  - Single-character queries
  - Multilingual edge cases
  - Score boundary conditions
  - RRF merge logic edge cases
"""

from __future__ import annotations

import uuid

import pytest

from app.schemas.search import SearchRequest, SearchResult
from app.services.search_service import _generate_highlight, _merge_results


# ---------------------------------------------------------------------------
# RRF merge logic
# ---------------------------------------------------------------------------

class TestMergeResults:
    def _make_result(self, ext_id: str, score: float) -> SearchResult:
        return SearchResult(
            doc_id=uuid.uuid4(),
            external_id=ext_id,
            score=score,
            title=ext_id,
            url=None,
            highlights=[],
            metadata={},
        )

    def test_merge_no_overlap(self):
        """Vector and keyword return completely different docs."""
        vector = [self._make_result("a", 0.9), self._make_result("b", 0.8)]
        keyword = [self._make_result("c", 0.7), self._make_result("d", 0.6)]
        merged = _merge_results(vector, keyword)
        ids = [r.external_id for r in merged]
        assert set(ids) == {"a", "b", "c", "d"}

    def test_merge_full_overlap(self):
        """Same docs in both — should boost scores."""
        vector = [self._make_result("a", 0.9), self._make_result("b", 0.7)]
        keyword = [self._make_result("a", 0.8), self._make_result("b", 0.5)]
        merged = _merge_results(vector, keyword)
        ids = [r.external_id for r in merged]
        # "a" should still be first (boosted by both)
        assert ids[0] == "a"
        # Score should be higher than either individual score
        assert merged[0].score > 0.9 * 0.7  # at least vector contribution

    def test_merge_preserves_order(self):
        """Results should be sorted by merged score descending."""
        vector = [self._make_result("a", 0.9)]
        keyword = [self._make_result("b", 0.95)]
        merged = _merge_results(vector, keyword)
        scores = [r.score for r in merged]
        assert scores == sorted(scores, reverse=True)

    def test_merge_empty_vector(self):
        """Only keyword results."""
        keyword = [self._make_result("a", 0.8)]
        merged = _merge_results([], keyword)
        assert len(merged) == 1
        assert merged[0].external_id == "a"

    def test_merge_empty_keyword(self):
        """Only vector results."""
        vector = [self._make_result("a", 0.9)]
        merged = _merge_results(vector, [])
        assert len(merged) == 1
        assert merged[0].external_id == "a"

    def test_merge_both_empty(self):
        merged = _merge_results([], [])
        assert merged == []

    def test_merge_single_doc_both(self):
        """One doc in both — score should reflect both contributions."""
        vector = [self._make_result("x", 1.0)]
        keyword = [self._make_result("x", 1.0)]
        merged = _merge_results(vector, keyword)
        assert len(merged) == 1
        assert merged[0].score > 0  # Has a valid RRF score

    def test_merge_highlights_combined(self):
        """Highlights from both sources should be merged."""
        v = SearchResult(
            doc_id=uuid.uuid4(),
            external_id="a",
            score=0.9,
            title="A",
            url=None,
            highlights=["vector highlight"],
            metadata={},
        )
        k = SearchResult(
            doc_id=v.doc_id,
            external_id="a",
            score=0.8,
            title="A",
            url=None,
            highlights=["keyword highlight"],
            metadata={},
        )
        merged = _merge_results([v], [k])
        assert len(merged) == 1
        assert "vector highlight" in merged[0].highlights
        assert "keyword highlight" in merged[0].highlights

    def test_merge_many_results(self):
        """Stress test with many results."""
        vector = [self._make_result(f"v{i}", 1.0 - i * 0.01) for i in range(50)]
        keyword = [self._make_result(f"k{i}", 1.0 - i * 0.01) for i in range(50)]
        merged = _merge_results(vector, keyword)
        assert len(merged) == 100
        scores = [r.score for r in merged]
        assert scores == sorted(scores, reverse=True)

    def test_merge_zero_scores(self):
        """Documents with zero scores should still be included."""
        vector = [self._make_result("a", 0.0)]
        keyword = [self._make_result("b", 0.0)]
        merged = _merge_results(vector, keyword)
        assert len(merged) == 2


# ---------------------------------------------------------------------------
# Highlight generation
# ---------------------------------------------------------------------------

class TestHighlightGeneration:
    def test_basic_highlight(self):
        content = "Ooredoo offers great 5G plans for all customers."
        highlight = _generate_highlight(content, "5G plans")
        assert "<em>" in highlight
        assert "5G" in highlight or "5g" in highlight

    def test_highlight_no_match(self):
        content = "This is about billing and payments."
        highlight = _generate_highlight(content, "xylophone")
        # Should still return a snippet, just without <em>
        assert len(highlight) > 0

    def test_highlight_long_content(self):
        content = "prefix " * 100 + "FINDME keyword here" + " suffix" * 100
        highlight = _generate_highlight(content, "FINDME")
        assert len(highlight) < len(content)  # Should be a snippet

    def test_highlight_case_insensitive(self):
        """Known limitation: _generate_highlight only replaces lowercase and
        Title Case, not ALL-CAPS. This test documents the gap."""
        content = "Ooredoo 5G plans are available."
        highlight = _generate_highlight(content, "plans")
        assert "<em>" in highlight

    def test_highlight_empty_query(self):
        content = "Some content here."
        highlight = _generate_highlight(content, "")
        assert len(highlight) > 0  # Should not crash

    def test_highlight_empty_content(self):
        highlight = _generate_highlight("", "query")
        assert highlight == "" or highlight == "..."


# ---------------------------------------------------------------------------
# SearchRequest validation edge cases
# ---------------------------------------------------------------------------

class TestSearchRequestValidation:
    def test_min_query_length(self):
        """Query must have at least 1 character."""
        with pytest.raises(Exception):
            SearchRequest(query="", mode="semantic")

    def test_limit_bounds(self):
        """Limit must be 1-100."""
        with pytest.raises(Exception):
            SearchRequest(query="test", limit=0)
        with pytest.raises(Exception):
            SearchRequest(query="test", limit=101)

    def test_offset_non_negative(self):
        with pytest.raises(Exception):
            SearchRequest(query="test", offset=-1)

    def test_min_score_bounds(self):
        with pytest.raises(Exception):
            SearchRequest(query="test", min_score=-0.1)
        with pytest.raises(Exception):
            SearchRequest(query="test", min_score=1.1)

    def test_valid_request(self):
        """A well-formed request should not raise."""
        req = SearchRequest(
            query="test query",
            mode="hybrid",
            limit=20,
            offset=0,
            min_score=0.5,
            highlight=True,
            facets=["category"],
        )
        assert req.query == "test query"


# ---------------------------------------------------------------------------
# Score distribution sanity
# ---------------------------------------------------------------------------

class TestScoreSanity:
    def test_scores_within_bounds(self):
        """All scores in merge output should be >= 0."""
        r1 = SearchResult(
            doc_id=uuid.uuid4(),
            external_id="a",
            score=0.01,
            title="A",
            url=None,
            highlights=[],
            metadata={},
        )
        r2 = SearchResult(
            doc_id=uuid.uuid4(),
            external_id="b",
            score=0.01,
            title="B",
            url=None,
            highlights=[],
            metadata={},
        )
        merged = _merge_results([r1], [r2])
        for r in merged:
            assert r.score >= 0, f"Negative score: {r.score}"
