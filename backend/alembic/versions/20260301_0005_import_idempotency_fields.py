"""import job idempotency fields

Revision ID: 20260301_0005
Revises: 20260301_0004
Create Date: 2026-03-01

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260301_0005"
down_revision: str | None = "20260301_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("import_jobs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("import_jobs", sa.Column("request_fingerprint", sa.String(length=128), nullable=True))
    op.create_index(
        "uq_import_job_project_idempotency",
        "import_jobs",
        ["project_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_import_job_project_idempotency", table_name="import_jobs")
    op.drop_column("import_jobs", "request_fingerprint")
    op.drop_column("import_jobs", "idempotency_key")
