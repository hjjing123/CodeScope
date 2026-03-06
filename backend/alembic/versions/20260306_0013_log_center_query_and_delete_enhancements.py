"""add log center query and delete enhancement columns

Revision ID: 20260306_0013
Revises: 20260304_0012
Create Date: 2026-03-06

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260306_0013"
down_revision: str | None = "20260304_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("system_logs", sa.Column("action_zh", sa.String(length=128), nullable=True))
    op.add_column(
        "system_logs", sa.Column("action_group", sa.String(length=64), nullable=True)
    )
    op.add_column("system_logs", sa.Column("summary_zh", sa.String(length=512), nullable=True))
    op.add_column(
        "system_logs",
        sa.Column("is_high_value", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_index(
        op.f("ix_system_logs_action_group"), "system_logs", ["action_group"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_is_high_value"),
        "system_logs",
        ["is_high_value"],
        unique=False,
    )
    op.create_index(
        "ix_system_logs_kind_occurred",
        "system_logs",
        ["log_kind", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_system_logs_kind_group_occurred",
        "system_logs",
        ["log_kind", "action_group", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_system_logs_kind_high_value_occurred",
        "system_logs",
        ["log_kind", "is_high_value", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_system_logs_request_kind_occurred",
        "system_logs",
        ["request_id", "log_kind", "occurred_at"],
        unique=False,
    )

    op.execute(
        """
        UPDATE system_logs
        SET
            action_group = NULL,
            action_zh = COALESCE(action, ''),
            summary_zh = COALESCE(action, ''),
            is_high_value = CASE
                WHEN log_kind = 'OPERATION' THEN TRUE
                WHEN level IN ('WARN', 'ERROR') THEN TRUE
                WHEN status_code >= 400 THEN TRUE
                WHEN duration_ms >= 1000 THEN TRUE
                ELSE FALSE
            END
        """
    )

    op.alter_column("system_logs", "is_high_value", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_system_logs_request_kind_occurred", table_name="system_logs")
    op.drop_index("ix_system_logs_kind_high_value_occurred", table_name="system_logs")
    op.drop_index("ix_system_logs_kind_group_occurred", table_name="system_logs")
    op.drop_index("ix_system_logs_kind_occurred", table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_is_high_value"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_action_group"), table_name="system_logs")

    op.drop_column("system_logs", "is_high_value")
    op.drop_column("system_logs", "summary_zh")
    op.drop_column("system_logs", "action_group")
    op.drop_column("system_logs", "action_zh")
