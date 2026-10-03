"""ensure the persisted second taxonomy level exists

Revision ID: item_subcategory_taxonomy_20261002
Revises: item_taxonomy_20261002
Create Date: 2026-10-02

Some long-lived installations predate ``items.subcategory`` entirely.  The
previous taxonomy migration correctly added the optional third-level columns,
but cannot persist a full hierarchy on those schemas until the mandatory
second-level column exists.  This follow-up is additive and safe for databases
that already have the column.
"""
from alembic import context, op
import sqlalchemy as sa


revision = "item_subcategory_taxonomy_20261002"
down_revision = "item_taxonomy_20261002"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table: str) -> set[str]:
    if context.is_offline_mode() or not _has_table(table):
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_table("items"):
        return

    columns = _columns("items")
    if "subcategory" not in columns:
        op.add_column("items", sa.Column("subcategory", sa.String(length=120), nullable=True))

    # The preceding migration creates this index where all three columns were
    # already present.  Create it here as well for older schemas that gained
    # ``subcategory`` only in this forward correction.
    columns = _columns("items")
    if {"category", "subcategory", "third_level"}.issubset(columns):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_items_category_subcategory_third_level "
            "ON items (category, subcategory, third_level)"
        )


def downgrade() -> None:
    # Keep the historic category/subcategory data intact on a rollback.  This
    # migration is intentionally forward-only for normal operations.
    return None
