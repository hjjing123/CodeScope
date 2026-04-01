"""normalize bootstrap admin identifier to admin

Revision ID: 20260331_0025
Revises: 20260330_0024
Create Date: 2026-03-31

"""

from __future__ import annotations

import os
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from alembic import op
from passlib.context import CryptContext
import sqlalchemy as sa


revision: str = "20260331_0025"
down_revision: str | None = "20260330_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
LEGACY_BOOTSTRAP_EMAIL = "admin@example.com"
DEFAULT_BOOTSTRAP_EMAIL = "admin"
DEFAULT_BOOTSTRAP_PASSWORD = "admin123"
DEFAULT_BOOTSTRAP_DISPLAY_NAME = "Bootstrap Admin"


def _bootstrap_admin_defaults() -> tuple[str, str, str]:
    email = (
        os.getenv("CODESCOPE_BOOTSTRAP_ADMIN_EMAIL", DEFAULT_BOOTSTRAP_EMAIL)
        .strip()
        .lower()
    )
    password = os.getenv(
        "CODESCOPE_BOOTSTRAP_ADMIN_PASSWORD", DEFAULT_BOOTSTRAP_PASSWORD
    ).strip()
    display_name = os.getenv(
        "CODESCOPE_BOOTSTRAP_ADMIN_DISPLAY_NAME",
        DEFAULT_BOOTSTRAP_DISPLAY_NAME,
    ).strip()

    if not email:
        email = DEFAULT_BOOTSTRAP_EMAIL
    if not password:
        password = DEFAULT_BOOTSTRAP_PASSWORD
    if not display_name:
        display_name = DEFAULT_BOOTSTRAP_DISPLAY_NAME

    return email, password, display_name


def _users_table() -> sa.Table:
    return sa.table(
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


def upgrade() -> None:
    bind = op.get_bind()
    users = _users_table()
    email, password, display_name = _bootstrap_admin_defaults()
    password_hash = pwd_context.hash(password)

    legacy_admin = bind.execute(
        sa.select(users.c.id).where(users.c.email == LEGACY_BOOTSTRAP_EMAIL)
    ).first()
    target_admin = bind.execute(
        sa.select(users.c.id).where(users.c.email == email)
    ).first()
    any_admin = bind.execute(
        sa.select(users.c.id).where(users.c.role == "Admin").limit(1)
    ).first()

    if legacy_admin is not None:
        update_values: dict[str, object] = {
            "display_name": display_name,
            "password_hash": password_hash,
            "role": "Admin",
            "is_active": True,
            "must_change_password": False,
        }
        if target_admin is None or target_admin.id == legacy_admin.id:
            update_values["email"] = email
        bind.execute(
            sa.update(users)
            .where(users.c.id == legacy_admin.id)
            .values(**update_values)
        )
        return

    if target_admin is not None:
        bind.execute(
            sa.update(users)
            .where(users.c.id == target_admin.id)
            .values(
                display_name=display_name,
                password_hash=password_hash,
                role="Admin",
                is_active=True,
                must_change_password=False,
            )
        )
        return

    if any_admin is None:
        bind.execute(
            sa.insert(users).values(
                id=uuid.uuid4(),
                email=email,
                password_hash=password_hash,
                display_name=display_name,
                role="Admin",
                is_active=True,
                must_change_password=False,
                created_at=datetime.now(timezone.utc),
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    users = _users_table()
    email, _, _ = _bootstrap_admin_defaults()
    bind.execute(
        sa.update(users)
        .where(users.c.email == email, users.c.role == "Admin")
        .values(email=LEGACY_BOOTSTRAP_EMAIL)
    )
