"""add ai assessment context and seeded sessions

Revision ID: 20260318_0022
Revises: 20260317_0021
Create Date: 2026-03-18

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260318_0022"
down_revision: str | None = "20260317_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "finding_ai_assessments",
        sa.Column(
            "request_messages_json", sa.JSON(), nullable=False, server_default="[]"
        ),
    )
    op.add_column(
        "finding_ai_assessments",
        sa.Column(
            "context_snapshot_json", sa.JSON(), nullable=False, server_default="{}"
        ),
    )
    op.alter_column(
        "finding_ai_assessments", "request_messages_json", server_default=None
    )
    op.alter_column(
        "finding_ai_assessments", "context_snapshot_json", server_default=None
    )

    op.add_column(
        "ai_chat_sessions",
        sa.Column("seed_kind", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ai_chat_sessions",
        sa.Column("seed_assessment_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_ai_chat_sessions_seed_assessment_id"),
        "ai_chat_sessions",
        ["seed_assessment_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_ai_chat_sessions_creator_seed_assessment",
        "ai_chat_sessions",
        ["created_by", "seed_assessment_id"],
    )
    op.create_foreign_key(
        "fk_ai_chat_sessions_seed_assessment_id_finding_ai_assessments",
        "ai_chat_sessions",
        "finding_ai_assessments",
        ["seed_assessment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ai_chat_sessions_seed_assessment_id_finding_ai_assessments",
        "ai_chat_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_ai_chat_sessions_creator_seed_assessment",
        "ai_chat_sessions",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_ai_chat_sessions_seed_assessment_id"),
        table_name="ai_chat_sessions",
    )
    op.drop_column("ai_chat_sessions", "seed_assessment_id")
    op.drop_column("ai_chat_sessions", "seed_kind")

    op.drop_column("finding_ai_assessments", "context_snapshot_json")
    op.drop_column("finding_ai_assessments", "request_messages_json")
