"""support general ai chat sessions

Revision ID: 20260316_0020
Revises: 20260316_0019
Create Date: 2026-03-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260316_0020"
down_revision: str | None = "20260316_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_chat_sessions",
        sa.Column(
            "session_mode",
            sa.String(length=32),
            nullable=True,
            server_default="finding_context",
        ),
    )
    op.execute("UPDATE ai_chat_sessions SET session_mode = 'finding_context'")

    with op.batch_alter_table("ai_chat_sessions") as batch_op:
        batch_op.alter_column("session_mode", nullable=False)
        batch_op.alter_column("finding_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.alter_column("project_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.alter_column("version_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.create_index(
            batch_op.f("ix_ai_chat_sessions_session_mode"),
            ["session_mode"],
            unique=False,
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ai_chat_messages WHERE session_id IN ("
        "SELECT id FROM ai_chat_sessions WHERE session_mode = 'general' OR finding_id IS NULL"
        ")"
    )
    op.execute(
        "DELETE FROM ai_chat_sessions WHERE session_mode = 'general' OR finding_id IS NULL"
    )

    with op.batch_alter_table("ai_chat_sessions") as batch_op:
        batch_op.drop_index(batch_op.f("ix_ai_chat_sessions_session_mode"))
        batch_op.alter_column("finding_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column("project_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column("version_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.drop_column("session_mode")
