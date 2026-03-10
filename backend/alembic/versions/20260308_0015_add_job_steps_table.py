"""add job steps table

Revision ID: 20260308_0015
Revises: 20260307_0014
Create Date: 2026-03-08

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260308_0015"
down_revision: str | None = "20260307_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "step_key", name="uq_job_steps_job_key"),
    )
    op.create_index(op.f("ix_job_steps_job_id"), "job_steps", ["job_id"], unique=False)
    op.create_index(op.f("ix_job_steps_status"), "job_steps", ["status"], unique=False)
    op.create_index(
        op.f("ix_job_steps_updated_at"), "job_steps", ["updated_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_job_steps_updated_at"), table_name="job_steps")
    op.drop_index(op.f("ix_job_steps_status"), table_name="job_steps")
    op.drop_index(op.f("ix_job_steps_job_id"), table_name="job_steps")
    op.drop_table("job_steps")
