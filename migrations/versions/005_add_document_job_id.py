"""Add job_id foreign key to documents table.

Links each document to the ingestion job that created it so the worker
processes only its own documents instead of all pending docs in the
collection.

Revision ID: 005
Revises: 004
Create Date: 2026-05-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "job_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_jobs.id"),
            nullable=True,
        ),
    )
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_documents_job_status "
            "ON documents (job_id, status)"
        )


def downgrade() -> None:
    op.drop_index("idx_documents_job_status", table_name="documents")
    op.drop_column("documents", "job_id")
