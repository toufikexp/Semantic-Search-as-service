"""Golden test dataset for search quality evaluation.

Provides curated queries with known-relevant documents and graded relevance
judgments for computing NDCG, MRR, Recall@k, and on-topic metrics.
"""

import uuid

# ---------------------------------------------------------------------------
# Document corpus — each entry represents an ingested, indexed document.
# ---------------------------------------------------------------------------
GOLDEN_DOCUMENTS = [
    {
        "external_id": "doc-python-intro",
        "title": "Introduction to Python Programming",
        "content": (
            "Python is a high-level, interpreted programming language known for "
            "its readability and versatile ecosystem. It supports multiple programming "
            "paradigms including procedural, object-oriented, and functional programming. "
            "Python is widely used in web development, data science, machine learning, "
            "and automation. Its simple syntax makes it ideal for beginners while "
            "its powerful libraries satisfy expert developers."
        ),
        "metadata": {"category": "programming", "language": "python", "level": "beginner"},
    },
    {
        "external_id": "doc-ml-basics",
        "title": "Machine Learning Fundamentals",
        "content": (
            "Machine learning is a subset of artificial intelligence that enables "
            "systems to learn from data without being explicitly programmed. "
            "Supervised learning uses labeled data, unsupervised learning discovers "
            "hidden patterns, and reinforcement learning optimizes through rewards. "
            "Common algorithms include linear regression, decision trees, random "
            "forests, support vector machines, and neural networks."
        ),
        "metadata": {"category": "ai", "topic": "machine-learning", "level": "intermediate"},
    },
    {
        "external_id": "doc-vector-db",
        "title": "Vector Databases and Semantic Search",
        "content": (
            "Vector databases store high-dimensional embeddings and support "
            "approximate nearest neighbor search for semantic similarity. "
            "They power modern search engines, recommendation systems, and RAG "
            "pipelines. Popular implementations include pgvector for PostgreSQL, "
            "Pinecone, Weaviate, and Qdrant. Cosine similarity and dot product "
            "are common distance metrics for comparing vectors."
        ),
        "metadata": {"category": "databases", "topic": "vector-search", "level": "advanced"},
    },
    {
        "external_id": "doc-fastapi",
        "title": "Building REST APIs with FastAPI",
        "content": (
            "FastAPI is a modern Python web framework for building APIs with "
            "automatic OpenAPI documentation. It leverages Python type hints for "
            "request validation and supports async/await natively. FastAPI is "
            "built on Starlette and Pydantic, providing high performance comparable "
            "to Node.js and Go frameworks."
        ),
        "metadata": {"category": "programming", "language": "python", "topic": "web"},
    },
    {
        "external_id": "doc-docker",
        "title": "Containerization with Docker",
        "content": (
            "Docker enables developers to package applications with their "
            "dependencies into portable containers. Docker Compose orchestrates "
            "multi-container applications. Containers provide consistent "
            "environments across development, testing, and production. "
            "Key concepts include images, containers, volumes, and networks."
        ),
        "metadata": {"category": "devops", "topic": "containers"},
    },
    {
        "external_id": "doc-nlp",
        "title": "Natural Language Processing Overview",
        "content": (
            "Natural language processing combines linguistics and machine "
            "learning to enable computers to understand human language. "
            "Key tasks include tokenization, named entity recognition, "
            "sentiment analysis, text classification, and machine translation. "
            "Transformer models like BERT and GPT have revolutionized NLP."
        ),
        "metadata": {"category": "ai", "topic": "nlp", "level": "intermediate"},
    },
    {
        "external_id": "doc-postgres",
        "title": "PostgreSQL Advanced Features",
        "content": (
            "PostgreSQL is a powerful open-source relational database with "
            "advanced features like JSONB, full-text search, window functions, "
            "CTEs, and extension support including pgvector for vector similarity "
            "search. It supports ACID transactions, multi-version concurrency "
            "control, and horizontal scaling via logical replication."
        ),
        "metadata": {"category": "databases", "topic": "sql", "level": "advanced"},
    },
    {
        "external_id": "doc-redis",
        "title": "Redis In-Memory Data Store",
        "content": (
            "Redis is an in-memory data structure store used as a database, "
            "cache, and message broker. It supports strings, hashes, lists, "
            "sets, sorted sets, streams, and more. Redis is commonly used for "
            "session management, rate limiting, real-time analytics, and task "
            "queue backends like Celery."
        ),
        "metadata": {"category": "databases", "topic": "nosql", "level": "intermediate"},
    },
]

# ---------------------------------------------------------------------------
# Evaluation queries with graded relevance judgments.
# Relevance scale:  3 = highly relevant,  2 = relevant,  1 = marginally,  0 = irrelevant
# ---------------------------------------------------------------------------
EVALUATION_QUERIES = [
    {
        "query": "semantic search with vector embeddings",
        "mode": "hybrid",
        "relevance": {
            "doc-vector-db": 3,
            "doc-postgres": 2,
            "doc-nlp": 1,
            "doc-ml-basics": 1,
        },
    },
    {
        "query": "Python web API framework",
        "mode": "hybrid",
        "relevance": {
            "doc-fastapi": 3,
            "doc-python-intro": 2,
        },
    },
    {
        "query": "machine learning algorithms neural networks",
        "mode": "hybrid",
        "relevance": {
            "doc-ml-basics": 3,
            "doc-nlp": 2,
            "doc-python-intro": 1,
        },
    },
    {
        "query": "database caching and task queues",
        "mode": "hybrid",
        "relevance": {
            "doc-redis": 3,
            "doc-postgres": 1,
        },
    },
    {
        "query": "containerize a web application",
        "mode": "hybrid",
        "relevance": {
            "doc-docker": 3,
            "doc-fastapi": 1,
        },
    },
]


def make_doc_id_map() -> dict[str, uuid.UUID]:
    """Create a deterministic external_id -> UUID mapping for test documents."""
    return {
        doc["external_id"]: uuid.uuid5(uuid.NAMESPACE_DNS, doc["external_id"])
        for doc in GOLDEN_DOCUMENTS
    }
