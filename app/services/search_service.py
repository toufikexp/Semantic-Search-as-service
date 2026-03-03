import logging
import time
import uuid

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.embedding import Embedding
from app.models.search_log import SearchLog
from app.schemas.search import (
    FacetValue,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SuggestRequest,
    SuggestResponse,
)

logger = logging.getLogger(__name__)


async def execute_search(
    db: AsyncSession,
    collection_id: uuid.UUID,
    request: SearchRequest,
    query_vector: list[float] | None = None,
) -> SearchResponse:
    """Execute a search query against a collection."""
    start_time = time.monotonic()
    query_id = uuid.uuid4()
    results: list[SearchResult] = []
    total = 0
    facets: dict = {}

    try:
        if request.mode in ("semantic", "hybrid") and query_vector is not None:
            results = await _vector_search(
                db, collection_id, query_vector, request
            )

        if request.mode in ("keyword", "hybrid"):
            keyword_results = await _keyword_search(db, collection_id, request)
            if request.mode == "hybrid" and results:
                results = _merge_results(results, keyword_results)
            elif not results:
                results = keyword_results

        # Apply min_score filter
        if request.min_score > 0:
            results = [r for r in results if r.score >= request.min_score]

        total = len(results)
        results = results[request.offset : request.offset + request.limit]

        # Compute facets
        if request.facets:
            facets = await _compute_facets(db, collection_id, request)
    finally:
        # Always log the search, even on partial failure
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        try:
            log_entry = SearchLog(
                collection_id=collection_id,
                query=request.query,
                mode=request.mode,
                filters=request.filters if request.filters else None,
                results_count=total,
                latency_ms=elapsed_ms,
            )
            db.add(log_entry)
            await db.commit()
        except Exception:
            logger.exception("Failed to write search log entry")

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    return SearchResponse(
        results=results,
        facets=facets,
        total=total,
        query_id=query_id,
        took_ms=elapsed_ms,
    )


async def _vector_search(
    db: AsyncSession,
    collection_id: uuid.UUID,
    query_vector: list[float],
    request: SearchRequest,
) -> list[SearchResult]:
    """Perform approximate nearest neighbor search using pgvector."""
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"
    limit = request.offset + request.limit

    sql = text("""
        SELECT
            d.id AS doc_id,
            d.external_id,
            d.title,
            d.url,
            d.metadata,
            c.content AS chunk_content,
            1 - (e.vector <=> CAST(:query_vector AS vector)) AS score
        FROM embeddings e
        JOIN chunks c ON c.id = e.chunk_id
        JOIN documents d ON d.id = c.document_id
        WHERE e.collection_id = :collection_id
          AND d.status = 'indexed'
        ORDER BY e.vector <=> CAST(:query_vector AS vector)
        LIMIT :limit
    """)

    result = await db.execute(
        sql,
        {
            "query_vector": vector_str,
            "collection_id": str(collection_id),
            "limit": limit,
        },
    )
    rows = result.fetchall()

    search_results = []
    seen_docs = set()
    for row in rows:
        if row.doc_id in seen_docs:
            continue
        seen_docs.add(row.doc_id)

        highlights = []
        if request.highlight and row.chunk_content:
            highlights = [_generate_highlight(row.chunk_content, request.query)]

        search_results.append(
            SearchResult(
                doc_id=row.doc_id,
                external_id=row.external_id,
                score=round(float(row.score), 4),
                title=row.title,
                url=row.url,
                highlights=highlights,
                metadata=row.metadata or {},
            )
        )

    return search_results


async def _keyword_search(
    db: AsyncSession,
    collection_id: uuid.UUID,
    request: SearchRequest,
) -> list[SearchResult]:
    """Perform full-text search using PostgreSQL tsvector."""
    limit = request.offset + request.limit
    tsquery = " & ".join(request.query.split())

    sql = text("""
        SELECT
            d.id AS doc_id,
            d.external_id,
            d.title,
            d.url,
            d.metadata,
            ts_rank(
                to_tsvector('english', coalesce(d.title, '') || ' ' || d.content),
                plainto_tsquery('english', :query)
            ) AS score,
            ts_headline(
                'english',
                d.content,
                plainto_tsquery('english', :query),
                'MaxWords=50, MinWords=20, StartSel=<em>, StopSel=</em>'
            ) AS highlight
        FROM documents d
        WHERE d.collection_id = :collection_id
          AND d.status = 'indexed'
          AND to_tsvector('english', coalesce(d.title, '') || ' ' || d.content)
              @@ plainto_tsquery('english', :query)
        ORDER BY score DESC
        LIMIT :limit
    """)

    result = await db.execute(
        sql,
        {
            "query": request.query,
            "collection_id": str(collection_id),
            "limit": limit,
        },
    )
    rows = result.fetchall()

    return [
        SearchResult(
            doc_id=row.doc_id,
            external_id=row.external_id,
            score=round(float(row.score), 4),
            title=row.title,
            url=row.url,
            highlights=[row.highlight] if row.highlight else [],
            metadata=row.metadata or {},
        )
        for row in rows
    ]


def _merge_results(
    vector_results: list[SearchResult],
    keyword_results: list[SearchResult],
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> list[SearchResult]:
    """Merge vector and keyword results using reciprocal rank fusion."""
    scores: dict[str, tuple[float, SearchResult]] = {}

    for rank, r in enumerate(vector_results):
        rrf_score = vector_weight / (rank + 60)
        scores[r.external_id] = (rrf_score, r)

    for rank, r in enumerate(keyword_results):
        rrf_score = keyword_weight / (rank + 60)
        if r.external_id in scores:
            existing_score, existing_result = scores[r.external_id]
            merged_score = existing_score + rrf_score
            # Combine highlights
            highlights = list(
                dict.fromkeys(existing_result.highlights + r.highlights)
            )
            scores[r.external_id] = (
                merged_score,
                SearchResult(
                    doc_id=existing_result.doc_id,
                    external_id=existing_result.external_id,
                    score=merged_score,
                    title=existing_result.title,
                    url=existing_result.url,
                    highlights=highlights,
                    metadata=existing_result.metadata,
                ),
            )
        else:
            scores[r.external_id] = (rrf_score, r)

    sorted_results = sorted(scores.values(), key=lambda x: x[0], reverse=True)

    # Normalize scores to 0-1 range so they are consistent and intuitive
    if not sorted_results:
        return []
    max_score = sorted_results[0][0]
    results = []
    for rrf_score, r in sorted_results:
        normalized = rrf_score / max_score if max_score > 0 else 0.0
        results.append(
            SearchResult(
                doc_id=r.doc_id,
                external_id=r.external_id,
                score=round(normalized, 4),
                title=r.title,
                url=r.url,
                highlights=r.highlights,
                metadata=r.metadata,
            )
        )
    return results


async def _compute_facets(
    db: AsyncSession,
    collection_id: uuid.UUID,
    request: SearchRequest,
) -> dict[str, list[FacetValue]]:
    """Compute facet counts from matching documents."""
    facets = {}
    for facet_field in request.facets:
        sql = text("""
            SELECT
                metadata->>:field AS value,
                COUNT(*) AS count
            FROM documents
            WHERE collection_id = :collection_id
              AND status = 'indexed'
              AND metadata ? :field
            GROUP BY metadata->>:field
            ORDER BY count DESC
            LIMIT 20
        """)
        result = await db.execute(
            sql,
            {"field": facet_field, "collection_id": str(collection_id)},
        )
        facets[facet_field] = [
            FacetValue(value=row.value, count=row.count)
            for row in result.fetchall()
            if row.value is not None
        ]

    return facets


def _generate_highlight(content: str, query: str) -> str:
    """Generate a simple highlight snippet from content."""
    words = query.lower().split()
    content_lower = content.lower()

    best_pos = 0
    for word in words:
        pos = content_lower.find(word)
        if pos >= 0:
            best_pos = pos
            break

    start = max(0, best_pos - 50)
    end = min(len(content), best_pos + 150)
    snippet = content[start:end]

    for word in words:
        snippet = snippet.replace(word, f"<em>{word}</em>")
        snippet = snippet.replace(word.capitalize(), f"<em>{word.capitalize()}</em>")

    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    return snippet


async def get_suggestions(
    db: AsyncSession,
    collection_id: uuid.UUID,
    request: SuggestRequest,
) -> SuggestResponse:
    """Return autocomplete suggestions based on document titles and past queries."""
    # Search document titles matching the prefix
    sql = text("""
        SELECT DISTINCT title
        FROM documents
        WHERE collection_id = :collection_id
          AND status = 'indexed'
          AND title ILIKE :prefix
        ORDER BY title
        LIMIT :limit
    """)
    result = await db.execute(
        sql,
        {
            "collection_id": str(collection_id),
            "prefix": f"{request.prefix}%",
            "limit": request.limit,
        },
    )
    title_suggestions = [row.title for row in result.fetchall() if row.title]

    # Also check popular past queries
    sql_queries = text("""
        SELECT query, COUNT(*) AS cnt
        FROM search_logs
        WHERE collection_id = :collection_id
          AND query ILIKE :prefix
        GROUP BY query
        ORDER BY cnt DESC
        LIMIT :limit
    """)
    result = await db.execute(
        sql_queries,
        {
            "collection_id": str(collection_id),
            "prefix": f"{request.prefix}%",
            "limit": request.limit,
        },
    )
    query_suggestions = [row.query for row in result.fetchall()]

    # Merge and deduplicate, prioritizing popular queries
    all_suggestions = list(dict.fromkeys(query_suggestions + title_suggestions))
    return SuggestResponse(suggestions=all_suggestions[: request.limit])
