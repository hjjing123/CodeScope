"""rule management tables

Revision ID: 20260302_0007
Revises: 20260301_0006
Create Date: 2026-03-02

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260302_0007"
down_revision: str | None = "20260301_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rules",
        sa.Column("rule_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("vuln_type", sa.String(length=64), nullable=False),
        sa.Column("default_severity", sa.String(length=16), nullable=False),
        sa.Column("language_scope", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("active_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("rule_key"),
    )
    op.create_index(op.f("ix_rules_enabled"), "rules", ["enabled"], unique=False)

    op.create_table(
        "rule_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rule_key"], ["rules.rule_key"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_key", "version", name="uq_rule_version"),
    )
    op.create_index(op.f("ix_rule_versions_rule_key"), "rule_versions", ["rule_key"], unique=False)

    op.create_table(
        "rule_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rule_sets_name"), "rule_sets", ["name"], unique=True)

    op.create_table(
        "rule_set_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(length=128), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rule_key"], ["rules.rule_key"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_set_id", "rule_key", name="uq_rule_set_rule_key"),
    )
    op.create_index(
        op.f("ix_rule_set_items_rule_set_id"),
        "rule_set_items",
        ["rule_set_id"],
        unique=False,
    )
    op.create_index(op.f("ix_rule_set_items_rule_key"), "rule_set_items", ["rule_key"], unique=False)

    op.create_table(
        "rule_stats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(length=128), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("avg_duration_ms", sa.Integer(), nullable=False),
        sa.Column("timeout_count", sa.Integer(), nullable=False),
        sa.Column("fp_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_key", "rule_version", "metric_date", name="uq_rule_stat_daily"),
    )
    op.create_index(op.f("ix_rule_stats_metric_date"), "rule_stats", ["metric_date"], unique=False)
    op.create_index(op.f("ix_rule_stats_rule_key"), "rule_stats", ["rule_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_rule_stats_rule_key"), table_name="rule_stats")
    op.drop_index(op.f("ix_rule_stats_metric_date"), table_name="rule_stats")
    op.drop_table("rule_stats")

    op.drop_index(op.f("ix_rule_set_items_rule_key"), table_name="rule_set_items")
    op.drop_index(op.f("ix_rule_set_items_rule_set_id"), table_name="rule_set_items")
    op.drop_table("rule_set_items")

    op.drop_index(op.f("ix_rule_sets_name"), table_name="rule_sets")
    op.drop_table("rule_sets")

    op.drop_index(op.f("ix_rule_versions_rule_key"), table_name="rule_versions")
    op.drop_table("rule_versions")

    op.drop_index(op.f("ix_rules_enabled"), table_name="rules")
    op.drop_table("rules")
