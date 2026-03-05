"""selftest jobs and finding extended fields

Revision ID: 20260302_0008
Revises: 20260302_0007
Create Date: 2026-03-02

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260302_0008"
down_revision: str | None = "20260302_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("rule_version", sa.Integer(), nullable=True))
    op.add_column("findings", sa.Column("vuln_type", sa.String(length=64), nullable=True))
    op.add_column("findings", sa.Column("file_path", sa.String(length=1024), nullable=True))
    op.add_column("findings", sa.Column("line_start", sa.Integer(), nullable=True))
    op.add_column("findings", sa.Column("line_end", sa.Integer(), nullable=True))
    op.add_column(
        "findings",
        sa.Column("has_path", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("findings", sa.Column("path_length", sa.Integer(), nullable=True))
    op.add_column("findings", sa.Column("source_file", sa.String(length=1024), nullable=True))
    op.add_column("findings", sa.Column("source_line", sa.Integer(), nullable=True))
    op.add_column("findings", sa.Column("sink_file", sa.String(length=1024), nullable=True))
    op.add_column("findings", sa.Column("sink_line", sa.Integer(), nullable=True))
    op.add_column(
        "findings",
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index(op.f("ix_findings_vuln_type"), "findings", ["vuln_type"], unique=False)
    op.create_index(op.f("ix_findings_file_path"), "findings", ["file_path"], unique=False)

    op.create_table(
        "selftest_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(length=128), nullable=True),
        sa.Column("rule_version", sa.Integer(), nullable=True),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_selftest_jobs_created_at"), "selftest_jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_selftest_jobs_rule_key"), "selftest_jobs", ["rule_key"], unique=False)
    op.create_index(op.f("ix_selftest_jobs_status"), "selftest_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_selftest_jobs_status"), table_name="selftest_jobs")
    op.drop_index(op.f("ix_selftest_jobs_rule_key"), table_name="selftest_jobs")
    op.drop_index(op.f("ix_selftest_jobs_created_at"), table_name="selftest_jobs")
    op.drop_table("selftest_jobs")

    op.drop_index(op.f("ix_findings_file_path"), table_name="findings")
    op.drop_index(op.f("ix_findings_vuln_type"), table_name="findings")
    op.drop_column("findings", "evidence_json")
    op.drop_column("findings", "sink_line")
    op.drop_column("findings", "sink_file")
    op.drop_column("findings", "source_line")
    op.drop_column("findings", "source_file")
    op.drop_column("findings", "path_length")
    op.drop_column("findings", "has_path")
    op.drop_column("findings", "line_end")
    op.drop_column("findings", "line_start")
    op.drop_column("findings", "file_path")
    op.drop_column("findings", "vuln_type")
    op.drop_column("findings", "rule_version")
