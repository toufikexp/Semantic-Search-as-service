"""Tests for document_service — ingest, get, delete, job status."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.schemas.document import DocumentInput
from app.services.document_service import (
    delete_document,
    get_document,
    get_job_status,
    ingest_documents,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def sample_docs():
    return [
        DocumentInput(
            external_id="ext-1",
            content="First document content.",
            title="Doc One",
            metadata={"category": "test"},
        ),
        DocumentInput(
            external_id="ext-2",
            content="Second document content.",
            title="Doc Two",
        ),
    ]


class TestIngestDocuments:
    async def test_creates_job(self, mock_db, sample_docs):
        col_id = uuid.uuid4()

        # Mock the select query to return no existing docs
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

        job = await ingest_documents(mock_db, col_id, sample_docs)
        assert isinstance(job, IngestionJob)
        assert job.total_docs == 2
        assert job.status == "processing"

    async def test_upsert_skips_unchanged(self, mock_db):
        """If content hash matches, the document should be skipped."""
        import hashlib

        content = "Same content."
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        col_id = uuid.uuid4()

        existing = MagicMock(spec=Document)
        existing.content_hash = content_hash

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

        docs = [DocumentInput(external_id="ext-1", content=content)]
        job = await ingest_documents(mock_db, col_id, docs, upsert=True)
        # processed_docs should be incremented because content is unchanged
        assert job.processed_docs == 1


class TestGetDocument:
    async def test_returns_document(self, mock_db):
        doc = MagicMock(spec=Document)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_document(mock_db, uuid.uuid4(), "ext-1")
        assert result is doc

    async def test_returns_none_when_missing(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_document(mock_db, uuid.uuid4(), "nonexistent")
        assert result is None


class TestDeleteDocument:
    async def test_deletes_existing(self, mock_db):
        doc = MagicMock(spec=Document)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await delete_document(mock_db, uuid.uuid4(), "ext-1")
        assert result is True
        mock_db.delete.assert_called_once_with(doc)

    async def test_returns_false_when_missing(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await delete_document(mock_db, uuid.uuid4(), "nonexistent")
        assert result is False


class TestGetJobStatus:
    async def test_returns_job(self, mock_db):
        job = MagicMock(spec=IngestionJob)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_job_status(mock_db, uuid.uuid4())
        assert result is job

    async def test_returns_none(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_job_status(mock_db, uuid.uuid4())
        assert result is None
