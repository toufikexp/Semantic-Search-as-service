"""Add callback_url and callback_secret to collections.

Allows collections to configure a webhook URL that receives a POST
notification when an ingestion job reaches a terminal state.

Revision ID: 004
Revises: 003
Create Date: 2026-04-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("collections", sa.Column("callback_url", sa.Text, nullable=True))
    op.add_column(
        "collections", sa.Column("callback_secret", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("collections", "callback_secret")
    op.drop_column("collections", "callback_url")
