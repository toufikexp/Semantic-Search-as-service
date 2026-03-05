"""Tests for core security utilities — API key generation and hashing."""

from app.core.security import API_KEY_PREFIX_MAP, generate_api_key, hash_api_key


class TestHashApiKey:
    def test_deterministic(self):
        assert hash_api_key("my-key") == hash_api_key("my-key")

    def test_hex_string(self):
        h = hash_api_key("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_keys_different_hashes(self):
        assert hash_api_key("key-a") != hash_api_key("key-b")


class TestGenerateApiKey:
    def test_returns_tuple(self):
        raw, key_hash = generate_api_key("master")
        assert isinstance(raw, str)
        assert isinstance(key_hash, str)

    def test_prefix_master(self):
        raw, _ = generate_api_key("master")
        assert raw.startswith("sk_master_")

    def test_prefix_ingest(self):
        raw, _ = generate_api_key("ingest")
        assert raw.startswith("sk_ingest_")

    def test_prefix_search(self):
        raw, _ = generate_api_key("search")
        assert raw.startswith("sk_search_")

    def test_unknown_scope_fallback(self):
        raw, _ = generate_api_key("custom")
        assert raw.startswith("sk_")

    def test_hash_matches_raw(self):
        raw, key_hash = generate_api_key("master")
        assert hash_api_key(raw) == key_hash

    def test_uniqueness(self):
        keys = {generate_api_key("search")[0] for _ in range(50)}
        assert len(keys) == 50

    def test_sufficient_length(self):
        raw, _ = generate_api_key("search")
        # prefix (~10) + 43 chars of base64 = ~53+ chars
        assert len(raw) >= 40
