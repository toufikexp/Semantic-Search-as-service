"""Add simple-config FTS index for multilingual keyword search.

The initial migration only created a GIN index using the 'english' text
search configuration.  Collections whose language is not English now use
a different PostgreSQL tsconfig (often 'simple'), which cannot leverage
that index.  This migration adds a second GIN index built with the
'simple' configuration so that non-English keyword queries can still
benefit from index-accelerated full-text search.

Revision ID: 003
Revises: 002
Create Date: 2026-03-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_fts_simple
        ON documents
        USING GIN (to_tsvector('simple', coalesce(title,'') || ' ' || content))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_fts_simple")
