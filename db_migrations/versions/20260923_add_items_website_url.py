"""add optional website URL to items

Revision ID: add_items_website_url_20260923
Revises: add_reports_and_is_mod_20251025
Create Date: 2026-09-23
"""

from alembic import context, op
import sqlalchemy as sa


revision = "add_items_website_url_20260923"
down_revision = "add_reports_and_is_mod_20251025"
branch_labels = None
depends_on = None


def _items_columns():
    if context.is_offline_mode():
        return set()
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns("items")}


def _dialect_name():
    if context.is_offline_mode():
        return context.get_context().dialect.name
    return op.get_bind().dialect.name


def upgrade():
    # PostgreSQL supports IF NOT EXISTS, which makes this safe alongside the
    # project's existing startup compatibility bridge.
    if _dialect_name() == "postgresql":
        op.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS website_url VARCHAR(2048)")
    elif "website_url" not in _items_columns():
        op.add_column("items", sa.Column("website_url", sa.String(length=2048), nullable=True))


def downgrade():
    if "website_url" in _items_columns():
        op.drop_column("items", "website_url")
