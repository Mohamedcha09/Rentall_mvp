"""add generic third-level listing taxonomy and Digital Accounts seed data

Revision ID: item_taxonomy_20261002
Revises: sevor_finder_20260929
Create Date: 2026-10-02

This is additive: existing items keep their category/subcategory values and
receive NULL for the optional third level.  It also backfills missing catalog
rows from legacy item values before seeding the new Digital Accounts branch;
it never rewrites or removes current categories or listings.
"""
from alembic import context, op
import sqlalchemy as sa

from app.catalog_taxonomy import DIGITAL_ACCOUNTS_CATEGORY, DIGITAL_ACCOUNTS_SERVICES


revision = "item_taxonomy_20261002"
down_revision = "sevor_finder_20260929"
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


def _backfill_legacy_catalog_rows() -> None:
    """Make pre-existing two-level items editable on a partially seeded DB.

    Older deployments can contain valid listing category/subcategory strings
    while their lookup tables have been lost or were never seeded.  New server
    validation intentionally relies on those lookup tables, so add only the
    exact missing lookup rows.  Listing values themselves are never changed.
    """
    required_tables = {"items", "categories", "subcategories"}
    if not all(_has_table(table) for table in required_tables):
        return
    item_columns = _columns("items")
    if "category" not in item_columns:
        return

    bind = op.get_bind()
    item_columns_for_query = [sa.column("category", sa.String)]
    if "subcategory" in item_columns:
        item_columns_for_query.append(sa.column("subcategory", sa.String))
    items = sa.table("items", *item_columns_for_query)
    categories = sa.table("categories", sa.column("id", sa.Integer), sa.column("name", sa.String))
    subcategories = sa.table(
        "subcategories",
        sa.column("id", sa.Integer),
        sa.column("category_id", sa.Integer),
        sa.column("name", sa.String),
    )

    def category_id_for(name: str) -> int:
        category_id = bind.execute(
            sa.select(categories.c.id).where(categories.c.name == name).limit(1)
        ).scalar()
        if category_id is None:
            bind.execute(categories.insert().values(name=name))
            category_id = bind.execute(
                sa.select(categories.c.id).where(categories.c.name == name).limit(1)
            ).scalar()
        return int(category_id)

    if "subcategory" in item_columns:
        rows = bind.execute(
            sa.select(sa.distinct(items.c.category), items.c.subcategory).where(
                items.c.category.is_not(None)
            )
        ).all()
    else:
        rows = [
            (row[0], None)
            for row in bind.execute(
                sa.select(sa.distinct(items.c.category)).where(items.c.category.is_not(None))
            ).all()
        ]
    for raw_category, raw_subcategory in rows:
        category_name = str(raw_category or "").strip()
        if not category_name:
            continue
        category_id = category_id_for(category_name)
        subcategory_name = str(raw_subcategory or "").strip()
        if not subcategory_name:
            continue
        existing = bind.execute(
            sa.select(subcategories.c.id).where(
                subcategories.c.category_id == category_id,
                subcategories.c.name == subcategory_name,
            ).limit(1)
        ).scalar()
        if existing is None:
            bind.execute(
                subcategories.insert().values(category_id=category_id, name=subcategory_name)
            )


def _seed_digital_accounts() -> None:
    """Idempotently add only the central Digital Accounts level 1/2 rows."""
    if not (_has_table("categories") and _has_table("subcategories")):
        return
    bind = op.get_bind()
    categories = sa.table("categories", sa.column("id", sa.Integer), sa.column("name", sa.String))
    subcategories = sa.table(
        "subcategories",
        sa.column("id", sa.Integer),
        sa.column("category_id", sa.Integer),
        sa.column("name", sa.String),
    )
    category_id = bind.execute(
        sa.select(categories.c.id).where(categories.c.name == DIGITAL_ACCOUNTS_CATEGORY)
    ).scalar_one_or_none()
    if category_id is None:
        bind.execute(categories.insert().values(name=DIGITAL_ACCOUNTS_CATEGORY))
        category_id = bind.execute(
            sa.select(categories.c.id).where(categories.c.name == DIGITAL_ACCOUNTS_CATEGORY)
        ).scalar_one()

    for digital_type in DIGITAL_ACCOUNTS_SERVICES:
        existing = bind.execute(
            sa.select(subcategories.c.id).where(
                subcategories.c.category_id == category_id,
                subcategories.c.name == digital_type,
            )
        ).scalar_one_or_none()
        if existing is None:
            bind.execute(subcategories.insert().values(category_id=category_id, name=digital_type))


def upgrade() -> None:
    if _has_table("items"):
        columns = _columns("items")
        if "third_level" not in columns:
            op.add_column("items", sa.Column("third_level", sa.String(length=160), nullable=True))
        if "custom_third_level" not in columns:
            op.add_column("items", sa.Column("custom_third_level", sa.String(length=200), nullable=True))

        # Helps Explore's three-level filtering without changing any existing
        # visibility/status index or query semantics.  A malformed test/legacy
        # schema without the historic category columns still receives the new
        # nullable fields, but does not fail while creating a composite index.
        index_columns = _columns("items")
        if {"category", "subcategory", "third_level"}.issubset(index_columns):
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_items_category_subcategory_third_level "
                "ON items (category, subcategory, third_level)"
            )

    # Keep existing two-level listings editable even if an old environment's
    # lookup tables are incomplete, then seed the new branch independently.
    _backfill_legacy_catalog_rows()
    _seed_digital_accounts()


def downgrade() -> None:
    # Do not delete catalog rows on rollback: they may already be referenced by
    # listings.  Only remove the additive index/columns after deliberate data
    # review.
    if not _has_table("items"):
        return
    op.execute("DROP INDEX IF EXISTS ix_items_category_subcategory_third_level")
    columns = _columns("items")
    if "custom_third_level" in columns:
        op.drop_column("items", "custom_third_level")
    if "third_level" in columns:
        op.drop_column("items", "third_level")
