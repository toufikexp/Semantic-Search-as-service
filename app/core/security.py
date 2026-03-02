import hashlib
import secrets

API_KEY_PREFIX_MAP = {
    "master": "sk_master_",
    "ingest": "sk_ingest_",
    "search": "sk_search_",
    "read": "sk_read_",
}


def generate_api_key(scope: str) -> tuple[str, str]:
    """Generate an API key and return (raw_key, key_hash)."""
    prefix = API_KEY_PREFIX_MAP.get(scope, "sk_")
    raw = prefix + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, key_hash


def hash_api_key(raw_key: str) -> str:
    """Hash an API key for storage/lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()
