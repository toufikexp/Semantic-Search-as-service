from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:changeme@localhost:5432/semantic_search"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql://postgres:changeme@localhost:5432/semantic_search"
    )
    DB_PASSWORD: str = "changeme"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    SECRET_KEY: str = "your-secret-key-change-in-production"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Embedding
    DEFAULT_EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_DEVICE: str = "auto"
    EMBEDDING_DIM: int = 1024
    EMBEDDING_CACHE_TTL: int = 3600  # seconds to cache query embeddings in Redis
    EMBEDDING_QUERY_TIMEOUT: int = 10  # seconds to wait for worker response

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True

    # Crawling
    MAX_CRAWL_PAGES: int = 500
    CRAWL_DELAY_SECONDS: float = 1.0

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


settings = Settings()
