"""add scan runtime and path tables

Revision ID: 20260310_0016
Revises: 20260308_0015
Create Date: 2026-03-10

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_0016"
down_revision: str | None = "20260308_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_runtime_leases",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id"),
        sa.UniqueConstraint("slot_index"),
    )
    op.create_index(
        op.f("ix_scan_runtime_leases_created_at"),
        "scan_runtime_leases",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "job_stream_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_job_stream_events_job_id"),
        "job_stream_events",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_stream_events_project_id"),
        "job_stream_events",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_stream_events_event_type"),
        "job_stream_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_stream_events_created_at"),
        "job_stream_events",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "finding_paths",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("path_order", sa.Integer(), nullable=False),
        sa.Column("path_length", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finding_id", "path_order", name="uq_finding_paths_order"),
    )
    op.create_index(
        op.f("ix_finding_paths_finding_id"),
        "finding_paths",
        ["finding_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finding_paths_created_at"),
        "finding_paths",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "finding_path_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_path_id", sa.Uuid(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("labels_json", sa.JSON(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("line_no", sa.Integer(), nullable=True),
        sa.Column("func_name", sa.String(length=255), nullable=True),
        sa.Column("code_snippet", sa.String(length=1024), nullable=True),
        sa.Column("node_ref", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_path_id"], ["finding_paths.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_path_id", "step_order", name="uq_finding_path_steps_order"
        ),
    )
    op.create_index(
        op.f("ix_finding_path_steps_finding_path_id"),
        "finding_path_steps",
        ["finding_path_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finding_path_steps_created_at"),
        "finding_path_steps",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_finding_path_steps_created_at"), table_name="finding_path_steps"
    )
    op.drop_index(
        op.f("ix_finding_path_steps_finding_path_id"), table_name="finding_path_steps"
    )
    op.drop_table("finding_path_steps")

    op.drop_index(op.f("ix_finding_paths_created_at"), table_name="finding_paths")
    op.drop_index(op.f("ix_finding_paths_finding_id"), table_name="finding_paths")
    op.drop_table("finding_paths")

    op.drop_index(
        op.f("ix_job_stream_events_created_at"), table_name="job_stream_events"
    )
    op.drop_index(
        op.f("ix_job_stream_events_event_type"), table_name="job_stream_events"
    )
    op.drop_index(
        op.f("ix_job_stream_events_project_id"), table_name="job_stream_events"
    )
    op.drop_index(op.f("ix_job_stream_events_job_id"), table_name="job_stream_events")
    op.drop_table("job_stream_events")

    op.drop_index(
        op.f("ix_scan_runtime_leases_created_at"), table_name="scan_runtime_leases"
    )
    op.drop_table("scan_runtime_leases")
