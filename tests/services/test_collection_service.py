"""Tests for collection_service — CRUD operations."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.collection import Collection
from app.schemas.collection import CollectionCreate, CollectionUpdate
from app.services.collection_service import (
    create_collection,
    delete_collection,
    get_collection,
    list_collections,
    update_collection,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


class TestCreateCollection:
    @patch("app.services.collection_service.generate_api_key")
    async def test_creates_collection_and_keys(self, mock_gen_key, mock_db):
        mock_gen_key.side_effect = [
            ("sk_ingest_raw", "hash_ingest"),
            ("sk_search_raw", "hash_search"),
        ]
        mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

        data = CollectionCreate(name="test-collection")
        org_id = uuid.uuid4()
        collection, keys = await create_collection(mock_db, org_id, data)

        assert isinstance(collection, Collection)
        assert collection.name == "test-collection"
        assert "ingest" in keys
        assert "search" in keys
        assert keys["ingest"] == "sk_ingest_raw"

    @patch("app.services.collection_service.generate_api_key")
    async def test_custom_chunk_strategy(self, mock_gen_key, mock_db):
        mock_gen_key.side_effect = [("raw1", "h1"), ("raw2", "h2")]
        mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

        data = CollectionCreate(
            name="my-col", chunk_strategy="sentence", chunk_size=256
        )
        collection, _ = await create_collection(mock_db, uuid.uuid4(), data)
        assert collection.chunk_strategy == "sentence"
        assert collection.chunk_size == 256


class TestGetCollection:
    async def test_returns_collection(self, mock_db):
        col = MagicMock(spec=Collection)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = col
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_collection(mock_db, uuid.uuid4())
        assert result is col

    async def test_returns_none(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_collection(mock_db, uuid.uuid4())
        assert result is None


class TestUpdateCollection:
    async def test_updates_fields(self, mock_db):
        col = MagicMock(spec=Collection)
        col.name = "old-name"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = col
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

        data = CollectionUpdate(name="new-name")
        result = await update_collection(mock_db, uuid.uuid4(), data)
        assert result is col

    async def test_returns_none_when_missing(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await update_collection(
            mock_db, uuid.uuid4(), CollectionUpdate(name="x")
        )
        assert result is None


class TestDeleteCollection:
    async def test_deletes_existing(self, mock_db):
        col = MagicMock(spec=Collection)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = col
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await delete_collection(mock_db, uuid.uuid4())
        assert result is True
        mock_db.delete.assert_called_once_with(col)

    async def test_returns_false_when_missing(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await delete_collection(mock_db, uuid.uuid4())
        assert result is False


class TestListCollections:
    async def test_returns_list_and_count(self, mock_db):
        # Mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 5

        # Mock list query
        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [MagicMock(spec=Collection) for _ in range(5)]
        list_result.scalars.return_value = scalars_mock

        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

        collections, total = await list_collections(mock_db, uuid.uuid4())
        assert total == 5
        assert len(collections) == 5
