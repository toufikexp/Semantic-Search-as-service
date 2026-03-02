from app.core.security import generate_api_key, hash_api_key


def test_generate_api_key_master():
    raw, hashed = generate_api_key("master")
    assert raw.startswith("sk_master_")
    assert len(hashed) == 64  # SHA-256 hex digest


def test_generate_api_key_ingest():
    raw, hashed = generate_api_key("ingest")
    assert raw.startswith("sk_ingest_")


def test_generate_api_key_search():
    raw, hashed = generate_api_key("search")
    assert raw.startswith("sk_search_")


def test_hash_api_key_consistency():
    raw, expected_hash = generate_api_key("master")
    assert hash_api_key(raw) == expected_hash


def test_unique_keys():
    _, hash1 = generate_api_key("master")
    _, hash2 = generate_api_key("master")
    assert hash1 != hash2
