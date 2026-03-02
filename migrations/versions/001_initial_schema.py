"""Initial schema with all tables, indexes, and pgvector extension.

Revision ID: 001
Revises: None
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")

    # Organizations
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("plan_tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("settings", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Collections
    op.create_table(
        "collections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("embedding_model", sa.String(50), server_default="bge-m3"),
        sa.Column("embedding_dim", sa.Integer, server_default="1024"),
        sa.Column("chunk_strategy", sa.String(30), server_default="adaptive"),
        sa.Column("chunk_size", sa.Integer, server_default="512"),
        sa.Column("chunk_overlap", sa.Integer, server_default="50"),
        sa.Column("metadata_schema", JSONB, server_default="{}"),
        sa.Column("language", sa.String(10), server_default="auto"),
        sa.Column("doc_count", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "name", name="uq_collection_org_name"),
    )

    # API Keys
    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("collections.id"), nullable=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("rate_limit", sa.Integer, server_default="60"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_api_keys_hash", "api_keys", ["key_hash"],
        postgresql_where=sa.text("is_active = true"),
    )

    # Documents
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_type", sa.String(20), server_default="text"),
        sa.Column("url", sa.Text),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("collection_id", "external_id", name="uq_document_collection_extid"),
    )
    op.execute("""
        CREATE INDEX idx_documents_fts ON documents
        USING GIN (to_tsvector('english', coalesce(title,'') || ' ' || content))
    """)
    op.create_index("idx_documents_metadata", "documents", ["metadata"], postgresql_using="gin")

    # Chunks
    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("collection_id", UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer),
        sa.Column("char_start", sa.Integer),
        sa.Column("char_end", sa.Integer),
        sa.Column("heading_context", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_chunks_doc", "chunks", ["collection_id", "document_id"])

    # Embeddings
    op.create_table(
        "embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection_id", UUID(as_uuid=True), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Add vector column (pgvector type)
    op.execute("ALTER TABLE embeddings ADD COLUMN vector vector(1024)")
    # HNSW index for approximate nearest neighbor search
    op.execute("""
        CREATE INDEX idx_embeddings_vector ON embeddings
        USING hnsw (vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 200)
    """)
    op.create_index("idx_embeddings_collection", "embeddings", ["collection_id"])

    # Ingestion Jobs
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("status", sa.String(20), server_default="processing"),
        sa.Column("total_docs", sa.Integer, server_default="0"),
        sa.Column("processed_docs", sa.Integer, server_default="0"),
        sa.Column("failed_docs", sa.Integer, server_default="0"),
        sa.Column("errors", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Search Logs
    op.create_table(
        "search_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("collection_id", UUID(as_uuid=True), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("mode", sa.String(20)),
        sa.Column("filters", JSONB),
        sa.Column("results_count", sa.Integer),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("clicked_doc_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_search_logs_time", "search_logs", ["collection_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_table("search_logs")
    op.drop_table("ingestion_jobs")
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("api_keys")
    op.drop_table("collections")
    op.drop_table("organizations")
    op.execute("DROP EXTENSION IF EXISTS btree_gin")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
