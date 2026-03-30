"""add report job generation fields

Revision ID: 20260321_0023
Revises: 20260318_0022
Create Date: 2026-03-21

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260321_0023"
down_revision: str | None = "20260318_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("report_job_id", sa.Uuid(), nullable=True))
    op.add_column("reports", sa.Column("finding_id", sa.Uuid(), nullable=True))
    op.add_column(
        "reports",
        sa.Column(
            "format",
            sa.String(length=32),
            nullable=False,
            server_default="MARKDOWN",
        ),
    )
    op.add_column("reports", sa.Column("created_by", sa.Uuid(), nullable=True))

    op.create_index(
        op.f("ix_reports_report_job_id"), "reports", ["report_job_id"], unique=False
    )
    op.create_index(
        op.f("ix_reports_finding_id"), "reports", ["finding_id"], unique=False
    )
    op.create_index(
        op.f("ix_reports_created_by"), "reports", ["created_by"], unique=False
    )
    op.create_foreign_key(
        "fk_reports_report_job_id_jobs",
        "reports",
        "jobs",
        ["report_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_reports_finding_id_findings",
        "reports",
        "findings",
        ["finding_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_reports_created_by_users",
        "reports",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("reports", "format", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_reports_created_by_users", "reports", type_="foreignkey")
    op.drop_constraint("fk_reports_finding_id_findings", "reports", type_="foreignkey")
    op.drop_constraint("fk_reports_report_job_id_jobs", "reports", type_="foreignkey")
    op.drop_index(op.f("ix_reports_created_by"), table_name="reports")
    op.drop_index(op.f("ix_reports_finding_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_report_job_id"), table_name="reports")
    op.drop_column("reports", "created_by")
    op.drop_column("reports", "format")
    op.drop_column("reports", "finding_id")
    op.drop_column("reports", "report_job_id")
