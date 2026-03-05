"""create unified system logs table

Revision ID: 20260304_0012
Revises: 20260304_0011
Create Date: 2026-03-04

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260304_0012"
down_revision: str | None = "20260304_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("log_kind", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("operator_user_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("task_type", sa.String(length=16), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=True),
        sa.Column("service", sa.String(length=32), nullable=True),
        sa.Column("module", sa.String(length=64), nullable=True),
        sa.Column("event", sa.String(length=128), nullable=True),
        sa.Column("message", sa.String(length=1024), nullable=True),
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
        op.f("ix_system_logs_action"), "system_logs", ["action"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_created_at"), "system_logs", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_error_code"), "system_logs", ["error_code"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_event"), "system_logs", ["event"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_level"), "system_logs", ["level"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_log_kind"), "system_logs", ["log_kind"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_module"), "system_logs", ["module"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_occurred_at"), "system_logs", ["occurred_at"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_operator_user_id"),
        "system_logs",
        ["operator_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_logs_project_id"), "system_logs", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_request_id"), "system_logs", ["request_id"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_service"), "system_logs", ["service"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_task_id"), "system_logs", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_system_logs_task_type"), "system_logs", ["task_type"], unique=False
    )

    op.execute(
        """
        INSERT INTO system_logs (
            id,
            log_kind,
            occurred_at,
            request_id,
            operator_user_id,
            project_id,
            task_type,
            task_id,
            action,
            resource_type,
            resource_id,
            result,
            level,
            service,
            module,
            event,
            message,
            status_code,
            duration_ms,
            error_code,
            detail_json,
            created_at
        )
        SELECT
            id,
            'OPERATION',
            created_at,
            request_id,
            operator_user_id,
            project_id,
            NULL,
            NULL,
            action,
            resource_type,
            resource_id,
            result,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            error_code,
            detail_json,
            created_at
        FROM audit_logs
        """
    )

    op.execute(
        """
        INSERT INTO system_logs (
            id,
            log_kind,
            occurred_at,
            request_id,
            operator_user_id,
            project_id,
            task_type,
            task_id,
            action,
            resource_type,
            resource_id,
            result,
            level,
            service,
            module,
            event,
            message,
            status_code,
            duration_ms,
            error_code,
            detail_json,
            created_at
        )
        SELECT
            id,
            'RUNTIME',
            occurred_at,
            request_id,
            operator_user_id,
            project_id,
            task_type,
            task_id,
            NULL,
            resource_type,
            resource_id,
            NULL,
            level,
            service,
            module,
            event,
            message,
            status_code,
            duration_ms,
            error_code,
            detail_json,
            created_at
        FROM runtime_logs
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_system_logs_task_type"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_task_id"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_service"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_request_id"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_project_id"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_operator_user_id"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_occurred_at"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_module"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_log_kind"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_level"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_event"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_error_code"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_created_at"), table_name="system_logs")
    op.drop_index(op.f("ix_system_logs_action"), table_name="system_logs")
    op.drop_table("system_logs")
