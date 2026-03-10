"""Fix ingestion_jobs.status column length: VARCHAR(20) -> VARCHAR(30).

The status value 'completed_with_errors' is 21 characters, which exceeds
the original VARCHAR(20) limit and causes a StringDataRightTruncation error.

Revision ID: 002
Revises: 001
Create Date: 2026-03-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: str = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "ingestion_jobs",
        "status",
        type_=sa.String(30),
        existing_type=sa.String(20),
    )


def downgrade() -> None:
    op.alter_column(
        "ingestion_jobs",
        "status",
        type_=sa.String(20),
        existing_type=sa.String(30),
    )
