"""add report metadata columns

Revision ID: 20260330_0024
Revises: 20260321_0023
Create Date: 2026-03-30

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260330_0024"
down_revision: str | None = "20260321_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column(
        "reports", sa.Column("template_key", sa.String(length=64), nullable=True)
    )
    op.add_column("reports", sa.Column("summary_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reports", "summary_text")
    op.drop_column("reports", "template_key")
    op.drop_column("reports", "title")
