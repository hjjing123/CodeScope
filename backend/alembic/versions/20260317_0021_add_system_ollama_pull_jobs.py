"""add system ollama pull jobs

Revision ID: 20260317_0021
Revises: 20260316_0020
Create Date: 2026-03-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260317_0021"
down_revision: str | None = "20260316_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_ollama_pull_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_hint", sa.String(length=1024), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["system_ai_providers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_system_ollama_pull_jobs_provider_id"),
        "system_ollama_pull_jobs",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_ollama_pull_jobs_model_name"),
        "system_ollama_pull_jobs",
        ["model_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_ollama_pull_jobs_status"),
        "system_ollama_pull_jobs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_ollama_pull_jobs_created_at"),
        "system_ollama_pull_jobs",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_system_ollama_pull_jobs_created_at"),
        table_name="system_ollama_pull_jobs",
    )
    op.drop_index(
        op.f("ix_system_ollama_pull_jobs_status"),
        table_name="system_ollama_pull_jobs",
    )
    op.drop_index(
        op.f("ix_system_ollama_pull_jobs_model_name"),
        table_name="system_ollama_pull_jobs",
    )
    op.drop_index(
        op.f("ix_system_ollama_pull_jobs_provider_id"),
        table_name="system_ollama_pull_jobs",
    )
    op.drop_table("system_ollama_pull_jobs")
