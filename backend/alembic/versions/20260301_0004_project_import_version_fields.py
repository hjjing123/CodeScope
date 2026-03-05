"""project import and version fields

Revision ID: 20260301_0004
Revises: 20260301_0003
Create Date: 2026-03-01

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260301_0004"
down_revision: str | None = "20260301_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("baseline_version_id", sa.Uuid(), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(op.f("ix_projects_baseline_version_id"), "projects", ["baseline_version_id"], unique=False)

    op.add_column("versions", sa.Column("note", sa.String(length=1024), nullable=True))
    op.add_column("versions", sa.Column("tag", sa.String(length=64), nullable=True))
    op.add_column("versions", sa.Column("git_repo_url", sa.String(length=1024), nullable=True))
    op.add_column("versions", sa.Column("git_ref", sa.String(length=255), nullable=True))
    op.add_column("versions", sa.Column("baseline_of_version_id", sa.Uuid(), nullable=True))
    op.add_column("versions", sa.Column("snapshot_object_key", sa.String(length=255), nullable=True))
    op.add_column(
        "versions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        op.f("ix_versions_baseline_of_version_id"), "versions", ["baseline_of_version_id"], unique=False
    )

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=True),
        sa.Column("import_type", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_import_jobs_created_at"), "import_jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_import_jobs_project_id"), "import_jobs", ["project_id"], unique=False)
    op.create_index(op.f("ix_import_jobs_status"), "import_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_import_jobs_version_id"), "import_jobs", ["version_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_import_jobs_version_id"), table_name="import_jobs")
    op.drop_index(op.f("ix_import_jobs_status"), table_name="import_jobs")
    op.drop_index(op.f("ix_import_jobs_project_id"), table_name="import_jobs")
    op.drop_index(op.f("ix_import_jobs_created_at"), table_name="import_jobs")
    op.drop_table("import_jobs")

    op.drop_index(op.f("ix_versions_baseline_of_version_id"), table_name="versions")
    op.drop_column("versions", "updated_at")
    op.drop_column("versions", "snapshot_object_key")
    op.drop_column("versions", "baseline_of_version_id")
    op.drop_column("versions", "git_ref")
    op.drop_column("versions", "git_repo_url")
    op.drop_column("versions", "tag")
    op.drop_column("versions", "note")

    op.drop_index(op.f("ix_projects_baseline_version_id"), table_name="projects")
    op.drop_column("projects", "updated_at")
    op.drop_column("projects", "baseline_version_id")
