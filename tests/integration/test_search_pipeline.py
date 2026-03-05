"""Integration tests for the search pipeline — keyword, semantic, hybrid flows."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import execute_search


class TestSearchPipelineKeyword:
    """Test keyword-only search flow through execute_search."""

    async def test_keyword_search_returns_response(self):
        db = AsyncMock()
        # Mock keyword search SQL result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()
        db.add = MagicMock()

        request = SearchRequest(query="test query", mode="keyword", limit=10)
        response = await execute_search(db, uuid.uuid4(), request, query_vector=None)

        assert isinstance(response, SearchResponse)
        assert response.total == 0
        assert response.results == []
        assert response.took_ms >= 0

    async def test_keyword_search_with_results(self):
        db = AsyncMock()
        row = MagicMock()
        row.doc_id = uuid.uuid4()
        row.external_id = "ext-1"
        row.title = "Test"
        row.url = None
        row.metadata = {}
        row.score = 0.75
        row.highlight = "Test <em>query</em> result"

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()
        db.add = MagicMock()

        request = SearchRequest(query="query", mode="keyword", limit=10)
        response = await execute_search(db, uuid.uuid4(), request)

        assert response.total == 1
        assert response.results[0].external_id == "ext-1"
        assert response.results[0].score == 0.75


class TestSearchPipelineHybrid:
    """Test hybrid search where both vector and keyword results merge."""

    async def test_hybrid_merges_results(self):
        db = AsyncMock()
        col_id = uuid.uuid4()

        # Vector search rows
        vec_row = MagicMock()
        vec_row.doc_id = uuid.uuid4()
        vec_row.external_id = "vec-doc"
        vec_row.title = "Vector Doc"
        vec_row.url = None
        vec_row.metadata = {}
        vec_row.chunk_content = "vector content"
        vec_row.score = 0.9

        # Keyword search rows
        kw_row = MagicMock()
        kw_row.doc_id = uuid.uuid4()
        kw_row.external_id = "kw-doc"
        kw_row.title = "Keyword Doc"
        kw_row.url = None
        kw_row.metadata = {}
        kw_row.score = 0.8
        kw_row.highlight = "keyword <em>match</em>"

        vec_result = MagicMock()
        vec_result.fetchall.return_value = [vec_row]
        kw_result = MagicMock()
        kw_result.fetchall.return_value = [kw_row]

        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return vec_result  # vector search
            elif call_count == 2:
                return kw_result  # keyword search
            else:
                return MagicMock(fetchall=MagicMock(return_value=[]))

        db.execute = mock_execute
        db.commit = AsyncMock()
        db.add = MagicMock()

        query_vector = [0.1] * 1024
        request = SearchRequest(query="test", mode="hybrid", limit=10)
        response = await execute_search(db, col_id, request, query_vector=query_vector)

        assert response.total >= 1
        ext_ids = {r.external_id for r in response.results}
        assert "vec-doc" in ext_ids or "kw-doc" in ext_ids


class TestSearchMinScore:
    """Verify min_score filtering works."""

    async def test_min_score_filters_low_results(self):
        db = AsyncMock()
        rows = []
        for i, score in enumerate([0.9, 0.5, 0.2]):
            row = MagicMock()
            row.doc_id = uuid.uuid4()
            row.external_id = f"doc-{i}"
            row.title = f"Doc {i}"
            row.url = None
            row.metadata = {}
            row.score = score
            row.highlight = ""
            rows.append(row)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()
        db.add = MagicMock()

        request = SearchRequest(query="test", mode="keyword", min_score=0.4)
        response = await execute_search(db, uuid.uuid4(), request)

        assert all(r.score >= 0.4 for r in response.results)


class TestSearchLogging:
    """Verify that searches are always logged."""

    async def test_search_log_created(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()
        db.add = MagicMock()

        request = SearchRequest(query="logged query", mode="keyword")
        await execute_search(db, uuid.uuid4(), request)

        # db.add should have been called with a SearchLog
        assert db.add.called
        log_arg = db.add.call_args[0][0]
        from app.models.search_log import SearchLog
        assert isinstance(log_arg, SearchLog)
        assert log_arg.query == "logged query"
