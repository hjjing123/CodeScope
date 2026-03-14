"""add finding path graph edges

Revision ID: 20260311_0017
Revises: 20260310_0016
Create Date: 2026-03-11

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260311_0017"
down_revision: str | None = "20260310_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "finding_path_steps",
        sa.Column("column_no", sa.Integer(), nullable=True),
    )
    op.add_column(
        "finding_path_steps",
        sa.Column("display_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "finding_path_steps",
        sa.Column("symbol_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "finding_path_steps",
        sa.Column("owner_method", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "finding_path_steps",
        sa.Column("type_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "finding_path_steps",
        sa.Column("node_kind", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "finding_path_steps",
        sa.Column(
            "raw_props_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )

    op.create_table(
        "finding_path_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_path_id", sa.Uuid(), nullable=False),
        sa.Column("edge_order", sa.Integer(), nullable=False),
        sa.Column("from_step_order", sa.Integer(), nullable=True),
        sa.Column("to_step_order", sa.Integer(), nullable=True),
        sa.Column("edge_type", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column(
            "is_hidden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "props_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_path_id"], ["finding_paths.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_path_id", "edge_order", name="uq_finding_path_edges_order"
        ),
    )
    op.create_index(
        op.f("ix_finding_path_edges_finding_path_id"),
        "finding_path_edges",
        ["finding_path_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finding_path_edges_created_at"),
        "finding_path_edges",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_finding_path_edges_created_at"),
        table_name="finding_path_edges",
    )
    op.drop_index(
        op.f("ix_finding_path_edges_finding_path_id"),
        table_name="finding_path_edges",
    )
    op.drop_table("finding_path_edges")

    op.drop_column("finding_path_steps", "raw_props_json")
    op.drop_column("finding_path_steps", "node_kind")
    op.drop_column("finding_path_steps", "type_name")
    op.drop_column("finding_path_steps", "owner_method")
    op.drop_column("finding_path_steps", "symbol_name")
    op.drop_column("finding_path_steps", "display_name")
    op.drop_column("finding_path_steps", "column_no")
