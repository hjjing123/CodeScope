"""migrate developer and redteam roles to user

Revision ID: 20260307_0014
Revises: 20260306_0013
Create Date: 2026-03-07

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260307_0014"
down_revision: str | None = "20260306_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET role = 'User'
        WHERE role IN ('Developer', 'RedTeam')
        """
    )


def downgrade() -> None:
    pass
