"""Integration tests for the document processing pipeline.

Tests the chunking -> embedding -> indexing workflow using mocked
infrastructure (no real DB/Redis/Celery, but real chunking logic).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import Document
from app.services.chunking_service import chunk_text


class TestDocumentProcessingPipeline:
    """Test the _process_single_document logic from tasks.py."""

    def _make_collection(self, **kwargs):
        col = MagicMock(spec=Collection)
        col.id = uuid.uuid4()
        col.chunk_strategy = kwargs.get("chunk_strategy", "adaptive")
        col.chunk_size = kwargs.get("chunk_size", 512)
        col.chunk_overlap = kwargs.get("chunk_overlap", 50)
        col.embedding_model = kwargs.get("embedding_model", "bge-m3")
        return col

    def _make_document(self, content: str = "Test content.", **kwargs):
        doc = MagicMock(spec=Document)
        doc.id = uuid.uuid4()
        doc.collection_id = uuid.uuid4()
        doc.external_id = kwargs.get("external_id", "test-doc")
        doc.content = content
        doc.status = "pending"
        doc.chunk_count = 0
        doc.indexed_at = None
        return doc

    def test_chunking_produces_valid_output(self):
        content = "First section.\n\nSecond section.\n\nThird section with more text."
        col = self._make_collection(chunk_strategy="paragraph")
        chunks = chunk_text(content, strategy=col.chunk_strategy, chunk_size=col.chunk_size)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.content.strip()
            assert chunk.token_count >= 0

    @patch("app.services.embedding_service._get_model")
    def test_embedding_follows_chunking(self, mock_get_model):
        from app.services.embedding_service import compute_embeddings

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(3, 1024).astype(np.float32)
        mock_get_model.return_value = mock_model

        content = "Paragraph one about Python.\n\nParagraph two about ML.\n\nParagraph three."
        chunks = chunk_text(content, strategy="paragraph", chunk_size=512)
        texts = [c.content for c in chunks]

        vectors = compute_embeddings(texts)
        assert len(vectors) == len(chunks)
        assert all(len(v) == 1024 for v in vectors)

    def test_all_strategies_produce_chunks(self):
        content = (
            "# Title\nIntro paragraph.\n\n"
            "## Section One\nFirst section content with detail.\n\n"
            "## Section Two\nSecond section content.\n\n"
            "Final paragraph."
        )
        for strategy in ["adaptive", "fixed", "sentence", "paragraph"]:
            chunks = chunk_text(content, strategy=strategy, chunk_size=512)
            assert len(chunks) >= 1, f"Strategy {strategy} produced no chunks"

    def test_heading_context_flows_through_adaptive(self):
        content = "# Main Heading\nContent under the main heading."
        chunks = chunk_text(content, strategy="adaptive", chunk_size=512)
        contextual = [c for c in chunks if c.heading_context]
        assert len(contextual) > 0

    def test_upsert_replaces_content(self):
        """Simulate the upsert flow: existing doc gets updated content."""
        doc = self._make_document(content="Old content.")
        new_content = "New updated content with more information."
        doc.content = new_content
        doc.status = "pending"

        chunks = chunk_text(doc.content, strategy="adaptive", chunk_size=512)
        assert len(chunks) >= 1
        assert "New updated" in chunks[0].content

    def test_empty_document_gets_zero_chunks(self):
        chunks = chunk_text("", strategy="adaptive", chunk_size=512)
        assert len(chunks) == 0


class TestCrawlUrlPatterns:
    """Test URL matching patterns used in crawl tasks."""

    def test_include_pattern(self):
        from app.workers.tasks import _url_matches_patterns

        assert _url_matches_patterns(
            "https://example.com/docs/api", ["*/docs/*"], []
        )
        assert not _url_matches_patterns(
            "https://example.com/blog/post", ["*/docs/*"], []
        )

    def test_exclude_pattern(self):
        from app.workers.tasks import _url_matches_patterns

        assert not _url_matches_patterns(
            "https://example.com/admin/panel", [], ["*/admin/*"]
        )
        assert _url_matches_patterns(
            "https://example.com/docs/api", [], ["*/admin/*"]
        )

    def test_no_patterns_allows_all(self):
        from app.workers.tasks import _url_matches_patterns

        assert _url_matches_patterns("https://any-url.com/path", [], [])

    def test_exclude_takes_precedence(self):
        from app.workers.tasks import _url_matches_patterns

        assert not _url_matches_patterns(
            "https://example.com/docs/secret",
            ["*/docs/*"],
            ["*secret*"],
        )
