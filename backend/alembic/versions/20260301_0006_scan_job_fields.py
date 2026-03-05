"""scan job fields and idempotency

Revision ID: 20260301_0006
Revises: 20260301_0005
Create Date: 2026-03-01

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260301_0006"
down_revision: str | None = "20260301_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("jobs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("jobs", sa.Column("request_fingerprint", sa.String(length=128), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("stage", sa.String(length=32), nullable=False, server_default=sa.text("'Prepare'")),
    )
    op.add_column("jobs", sa.Column("failure_code", sa.String(length=64), nullable=True))
    op.add_column("jobs", sa.Column("failure_stage", sa.String(length=32), nullable=True))
    op.add_column("jobs", sa.Column("failure_category", sa.String(length=32), nullable=True))
    op.add_column("jobs", sa.Column("failure_hint", sa.String(length=1024), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("result_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "created_by",
            sa.Uuid(),
            nullable=True,
        ),
    )
    op.add_column("jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_jobs_created_by_users",
            "jobs",
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_index(op.f("ix_jobs_created_at"), "jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_jobs_job_type"), "jobs", ["job_type"], unique=False)
    op.create_index(op.f("ix_jobs_started_at"), "jobs", ["started_at"], unique=False)
    op.create_index(op.f("ix_jobs_finished_at"), "jobs", ["finished_at"], unique=False)
    op.create_index(
        "uq_job_project_type_idempotency",
        "jobs",
        ["project_id", "job_type", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_job_project_type_idempotency", table_name="jobs")
    op.drop_index(op.f("ix_jobs_finished_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_started_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_job_type"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_created_at"), table_name="jobs")

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_jobs_created_by_users", "jobs", type_="foreignkey")

    op.drop_column("jobs", "updated_at")
    op.drop_column("jobs", "finished_at")
    op.drop_column("jobs", "started_at")
    op.drop_column("jobs", "created_by")
    op.drop_column("jobs", "result_summary")
    op.drop_column("jobs", "failure_hint")
    op.drop_column("jobs", "failure_category")
    op.drop_column("jobs", "failure_stage")
    op.drop_column("jobs", "failure_code")
    op.drop_column("jobs", "stage")
    op.drop_column("jobs", "request_fingerprint")
    op.drop_column("jobs", "idempotency_key")
    op.drop_column("jobs", "payload")
