"""Shared fixtures for evaluation tests."""

import uuid

import pytest

from tests.evaluation.golden_dataset import DOCUMENTS, GOLDEN_QUERIES, GoldenQuery


@pytest.fixture
def golden_queries() -> list[GoldenQuery]:
    return GOLDEN_QUERIES


@pytest.fixture
def golden_documents():
    return DOCUMENTS


@pytest.fixture
def sample_collection_id() -> uuid.UUID:
    return uuid.UUID("18430ccb-ef03-428f-992a-6f1f104dc3aa")
