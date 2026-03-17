"""add ai runtime tables

Revision ID: 20260316_0019
Revises: 20260314_0018
Create Date: 2026-03-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260316_0019"
down_revision: str | None = "20260314_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_ai_providers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=1024), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("default_model", sa.String(length=255), nullable=True),
        sa.Column("published_models_json", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_key"),
    )
    op.create_index(
        op.f("ix_system_ai_providers_provider_key"),
        "system_ai_providers",
        ["provider_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_system_ai_providers_created_at"),
        "system_ai_providers",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "user_ai_providers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("vendor_name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=1024), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("default_model", sa.String(length=255), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "display_name",
            name="uq_user_ai_providers_user_display_name",
        ),
    )
    op.create_index(
        op.f("ix_user_ai_providers_user_id"),
        "user_ai_providers",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_ai_providers_created_at"),
        "user_ai_providers",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "finding_ai_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("scan_job_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("provider_source", sa.String(length=64), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("provider_label", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_id",
            "job_id",
            name="uq_finding_ai_assessments_finding_job",
        ),
    )
    op.create_index(
        op.f("ix_finding_ai_assessments_finding_id"),
        "finding_ai_assessments",
        ["finding_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finding_ai_assessments_job_id"),
        "finding_ai_assessments",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finding_ai_assessments_scan_job_id"),
        "finding_ai_assessments",
        ["scan_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finding_ai_assessments_project_id"),
        "finding_ai_assessments",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finding_ai_assessments_version_id"),
        "finding_ai_assessments",
        ["version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finding_ai_assessments_status"),
        "finding_ai_assessments",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finding_ai_assessments_created_at"),
        "finding_ai_assessments",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "ai_chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("provider_source", sa.String(length=64), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("provider_label", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("provider_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_chat_sessions_finding_id"),
        "ai_chat_sessions",
        ["finding_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_chat_sessions_project_id"),
        "ai_chat_sessions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_chat_sessions_version_id"),
        "ai_chat_sessions",
        ["version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_chat_sessions_created_by"),
        "ai_chat_sessions",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_chat_sessions_created_at"),
        "ai_chat_sessions",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "ai_chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["ai_chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_chat_messages_session_id"),
        "ai_chat_messages",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_chat_messages_created_at"),
        "ai_chat_messages",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_chat_messages_created_at"), table_name="ai_chat_messages")
    op.drop_index(op.f("ix_ai_chat_messages_session_id"), table_name="ai_chat_messages")
    op.drop_table("ai_chat_messages")

    op.drop_index(op.f("ix_ai_chat_sessions_created_at"), table_name="ai_chat_sessions")
    op.drop_index(op.f("ix_ai_chat_sessions_created_by"), table_name="ai_chat_sessions")
    op.drop_index(op.f("ix_ai_chat_sessions_version_id"), table_name="ai_chat_sessions")
    op.drop_index(op.f("ix_ai_chat_sessions_project_id"), table_name="ai_chat_sessions")
    op.drop_index(op.f("ix_ai_chat_sessions_finding_id"), table_name="ai_chat_sessions")
    op.drop_table("ai_chat_sessions")

    op.drop_index(
        op.f("ix_finding_ai_assessments_created_at"),
        table_name="finding_ai_assessments",
    )
    op.drop_index(
        op.f("ix_finding_ai_assessments_status"),
        table_name="finding_ai_assessments",
    )
    op.drop_index(
        op.f("ix_finding_ai_assessments_version_id"),
        table_name="finding_ai_assessments",
    )
    op.drop_index(
        op.f("ix_finding_ai_assessments_project_id"),
        table_name="finding_ai_assessments",
    )
    op.drop_index(
        op.f("ix_finding_ai_assessments_scan_job_id"),
        table_name="finding_ai_assessments",
    )
    op.drop_index(
        op.f("ix_finding_ai_assessments_job_id"),
        table_name="finding_ai_assessments",
    )
    op.drop_index(
        op.f("ix_finding_ai_assessments_finding_id"),
        table_name="finding_ai_assessments",
    )
    op.drop_table("finding_ai_assessments")

    op.drop_index(
        op.f("ix_user_ai_providers_created_at"), table_name="user_ai_providers"
    )
    op.drop_index(op.f("ix_user_ai_providers_user_id"), table_name="user_ai_providers")
    op.drop_table("user_ai_providers")

    op.drop_index(
        op.f("ix_system_ai_providers_created_at"), table_name="system_ai_providers"
    )
    op.drop_index(
        op.f("ix_system_ai_providers_provider_key"),
        table_name="system_ai_providers",
    )
    op.drop_table("system_ai_providers")
