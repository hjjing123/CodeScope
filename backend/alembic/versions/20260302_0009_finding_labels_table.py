"""add finding labels table

Revision ID: 20260302_0009
Revises: 20260302_0008
Create Date: 2026-03-02

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260302_0009"
down_revision: str | None = "20260302_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finding_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("fp_reason", sa.String(length=64), nullable=True),
        sa.Column("comment", sa.String(length=1024), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_finding_labels_created_at"), "finding_labels", ["created_at"], unique=False)
    op.create_index(op.f("ix_finding_labels_finding_id"), "finding_labels", ["finding_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_finding_labels_finding_id"), table_name="finding_labels")
    op.drop_index(op.f("ix_finding_labels_created_at"), table_name="finding_labels")
    op.drop_table("finding_labels")
