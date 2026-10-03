"""correct the persisted Digital Accounts level-two catalog

Revision ID: digital_catalog_20261003
Revises: item_subcat_taxonomy_20261002
Create Date: 2026-10-03

This targeted, additive correction is intentionally independent of the mutable
application catalog.  It only touches the Digital Accounts lookup branch and
the matching legacy Item strings needed to keep existing listings valid after
the canonical ``General`` name becomes ``General Subscriptions``.
"""
from alembic import context, op
import sqlalchemy as sa


revision = "digital_catalog_20261003"
down_revision = "item_subcat_taxonomy_20261002"
branch_labels = None
depends_on = None


DIGITAL_ACCOUNTS = "Digital Accounts"
GENERAL_LEGACY = "General"
GENERAL_CANONICAL = "General Subscriptions"

# Keep this a snapshot rather than importing app.catalog_taxonomy.  Historical
# migrations must not change their behavior when application catalog code does.
CANONICAL_TYPES = (
    "Movies & Streaming",
    "Sports",
    "Gaming",
    "Music & Audio",
    "AI Tools",
    "Software & Productivity",
    "Design / Photo / Video",
    "Cloud & Storage",
    "Education",
    "News & Reading",
    "Social & Creator",
    "Business & Marketing",
    "Hosting & Developer",
    "VPN & Security",
    "Regional TV & Entertainment",
    GENERAL_CANONICAL,
    "Other",
)

LEGACY_SERVICE_RENAMES = (
    ("Movies & Streaming", "BBC-related paid services", "BBC-related paid services where available"),
    ("AI Tools", "Character.AI", "Character.AI paid plans"),
    ("Regional TV & Entertainment", "ZEE5", "Zee5"),
)


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table: str) -> set[str]:
    if context.is_offline_mode() or not _has_table(table):
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _lock_digital_catalog(bind) -> None:
    """Serialize the get-or-create path where the child table lacks a key."""
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": DIGITAL_ACCOUNTS})


def _single_category_id(bind, categories) -> int | None:
    ids = bind.execute(
        sa.select(categories.c.id).where(categories.c.name == DIGITAL_ACCOUNTS)
    ).scalars().all()
    if len(ids) > 1:
        raise RuntimeError("Digital Accounts has duplicate category rows; refusing an ambiguous taxonomy migration.")
    return int(ids[0]) if ids else None


def _assert_unique_types(bind, subcategories, category_id: int) -> None:
    duplicates = bind.execute(
        sa.select(subcategories.c.name)
        .where(subcategories.c.category_id == category_id)
        .group_by(subcategories.c.name)
        .having(sa.func.count(subcategories.c.id) > 1)
    ).scalars().all()
    if duplicates:
        raise RuntimeError("Digital Accounts has duplicate subcategory rows; refusing an ambiguous taxonomy migration.")


def _rename_general(bind, subcategories, items, category_id: int, item_columns: set[str]) -> None:
    present = set(
        bind.execute(
            sa.select(subcategories.c.name).where(
                subcategories.c.category_id == category_id,
                subcategories.c.name.in_((GENERAL_LEGACY, GENERAL_CANONICAL)),
            )
        ).scalars().all()
    )
    if GENERAL_LEGACY in present and GENERAL_CANONICAL in present:
        raise RuntimeError(
            "Both General and General Subscriptions exist under Digital Accounts; refusing to merge rows automatically."
        )
    if GENERAL_LEGACY not in present:
        return

    if "subcategory" in item_columns and "category" not in item_columns:
        raise RuntimeError("Cannot safely rename legacy General item values without items.category.")
    if {"category", "subcategory"}.issubset(item_columns):
        bind.execute(
            items.update()
            .where(
                items.c.category == DIGITAL_ACCOUNTS,
                items.c.subcategory == GENERAL_LEGACY,
            )
            .values(subcategory=GENERAL_CANONICAL)
        )
    bind.execute(
        subcategories.update()
        .where(
            subcategories.c.category_id == category_id,
            subcategories.c.name == GENERAL_LEGACY,
        )
        .values(name=GENERAL_CANONICAL)
    )


def _rename_legacy_services(bind, items, item_columns: set[str]) -> None:
    required = {"category", "subcategory", "third_level"}
    if not required.issubset(item_columns):
        return
    for subcategory, legacy_value, canonical_value in LEGACY_SERVICE_RENAMES:
        bind.execute(
            items.update()
            .where(
                items.c.category == DIGITAL_ACCOUNTS,
                items.c.subcategory == subcategory,
                items.c.third_level == legacy_value,
            )
            .values(third_level=canonical_value)
        )


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("digital_catalog_20261003 must run online against the target database.")
    if not (_has_table("categories") and _has_table("subcategories")):
        return

    bind = op.get_bind()
    _lock_digital_catalog(bind)
    categories = sa.table("categories", sa.column("id", sa.Integer), sa.column("name", sa.String))
    subcategories = sa.table(
        "subcategories",
        sa.column("id", sa.Integer),
        sa.column("category_id", sa.Integer),
        sa.column("name", sa.String),
    )
    item_columns = _columns("items")
    items = sa.table(
        "items",
        sa.column("category", sa.String),
        sa.column("subcategory", sa.String),
        sa.column("third_level", sa.String),
    )

    category_id = _single_category_id(bind, categories)
    if category_id is None:
        bind.execute(categories.insert().values(name=DIGITAL_ACCOUNTS))
        category_id = _single_category_id(bind, categories)
    if category_id is None:
        raise RuntimeError("Digital Accounts category could not be created.")

    _assert_unique_types(bind, subcategories, category_id)
    _rename_general(bind, subcategories, items, category_id, item_columns)
    _rename_legacy_services(bind, items, item_columns)

    existing = set(
        bind.execute(
            sa.select(subcategories.c.name).where(subcategories.c.category_id == category_id)
        ).scalars().all()
    )
    for name in CANONICAL_TYPES:
        if name not in existing:
            bind.execute(subcategories.insert().values(category_id=category_id, name=name))


def downgrade() -> None:
    # Do not remove lookup data or rewrite listing values during a rollback.
    return None
