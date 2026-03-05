"""add runtime logs and task log index tables

Revision ID: 20260304_0011
Revises: 20260303_0010
Create Date: 2026-03-04

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260304_0011"
down_revision: str | None = "20260303_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("service", sa.String(length=32), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("event", sa.String(length=128), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("operator_user_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("task_type", sa.String(length=16), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("detail_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operator_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_runtime_logs_created_at"), "runtime_logs", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_runtime_logs_error_code"), "runtime_logs", ["error_code"], unique=False
    )
    op.create_index(
        op.f("ix_runtime_logs_event"), "runtime_logs", ["event"], unique=False
    )
    op.create_index(
        op.f("ix_runtime_logs_level"), "runtime_logs", ["level"], unique=False
    )
    op.create_index(
        op.f("ix_runtime_logs_module"), "runtime_logs", ["module"], unique=False
    )
    op.create_index(
        op.f("ix_runtime_logs_occurred_at"),
        "runtime_logs",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_logs_operator_user_id"),
        "runtime_logs",
        ["operator_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_logs_project_id"), "runtime_logs", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_runtime_logs_request_id"), "runtime_logs", ["request_id"], unique=False
    )
    op.create_index(
        op.f("ix_runtime_logs_service"), "runtime_logs", ["service"], unique=False
    )
    op.create_index(
        op.f("ix_runtime_logs_task_id"), "runtime_logs", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_runtime_logs_task_type"), "runtime_logs", ["task_type"], unique=False
    )

    op.create_table(
        "task_log_index",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=16), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("storage_backend", sa.String(length=16), nullable=False),
        sa.Column("object_key", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_type", "task_id", "stage", name="uq_task_log_index_task_stage"
        ),
    )
    op.create_index(
        op.f("ix_task_log_index_project_id"),
        "task_log_index",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_log_index_task_id"), "task_log_index", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_task_log_index_task_type"),
        "task_log_index",
        ["task_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_log_index_updated_at"),
        "task_log_index",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_log_index_updated_at"), table_name="task_log_index")
    op.drop_index(op.f("ix_task_log_index_task_type"), table_name="task_log_index")
    op.drop_index(op.f("ix_task_log_index_task_id"), table_name="task_log_index")
    op.drop_index(op.f("ix_task_log_index_project_id"), table_name="task_log_index")
    op.drop_table("task_log_index")

    op.drop_index(op.f("ix_runtime_logs_task_type"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_task_id"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_service"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_request_id"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_project_id"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_operator_user_id"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_occurred_at"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_module"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_level"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_event"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_error_code"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_created_at"), table_name="runtime_logs")
    op.drop_table("runtime_logs")
