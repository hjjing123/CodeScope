"""bootstrap admin seed and first-login password reset flag

Revision ID: 20260301_0002
Revises: 20260301_0001
Create Date: 2026-03-01

"""

from __future__ import annotations

import os
import uuid
from collections.abc import Sequence
from datetime import datetime

from alembic import op
from passlib.context import CryptContext
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260301_0002"
down_revision: str | None = "20260301_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _seed_bootstrap_admin() -> None:
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("email", sa.String()),
        sa.column("password_hash", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("role", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("must_change_password", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    has_admin = bind.execute(
        sa.select(sa.func.count()).select_from(users).where(users.c.role == "Admin")
    ).scalar_one()
    if has_admin and int(has_admin) > 0:
        return

    admin_email = os.getenv("CODESCOPE_BOOTSTRAP_ADMIN_EMAIL", "admin@codescope.local").strip().lower()
    admin_password = os.getenv("CODESCOPE_BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe123!").strip()
    display_name = os.getenv("CODESCOPE_BOOTSTRAP_ADMIN_DISPLAY_NAME", "Bootstrap Admin").strip()
    now = datetime.utcnow()

    existing = bind.execute(sa.select(users.c.id).where(users.c.email == admin_email)).first()

    if existing is not None:
        bind.execute(
            sa.update(users)
            .where(users.c.id == existing.id)
            .values(
                role="Admin",
                is_active=True,
                display_name=display_name,
                password_hash=pwd_context.hash(admin_password),
                must_change_password=True,
            )
        )
        return

    bind.execute(
        sa.insert(users).values(
            id=uuid.uuid4(),
            email=admin_email,
            password_hash=pwd_context.hash(admin_password),
            display_name=display_name,
            role="Admin",
            is_active=True,
            must_change_password=True,
            created_at=now,
        )
    )


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _seed_bootstrap_admin()


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
