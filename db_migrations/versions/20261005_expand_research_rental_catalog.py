"""seed the additive research-backed rental catalog branches

Revision ID: research_catalog_20261005
Revises: merge_taxonomy_20261004
Create Date: 2026-10-05

This is an additive, immutable L1/L2 snapshot for the research-backed rental
catalog extension.  It deliberately does not import ``app.rental_catalog``:
historical migrations must not change their meaning when the live catalog
changes later.  L3 values continue to be centrally defined in application
code because the current schema has no L3 lookup table.

The migration inserts only missing category/subcategory lookup rows.  It does
not delete, rename, reorder, or reclassify Items, categories, or subcategories.
It detects an ambiguous parent or duplicate L2 rows and rolls back instead of
guessing which existing record should be used.
"""
from alembic import context, op
import sqlalchemy as sa


revision = "research_catalog_20261005"
down_revision = "merge_taxonomy_20261004"
branch_labels = None
depends_on = None


# Immutable L1/L2 delta from the 2026-10-05 research extension.  This is a
# delta, not a replacement for the earlier rental catalog snapshot.
CATEGORY_SEED = (
    ("Vehicles", ("vehicle",), ("Vehicle Travel Accessories",)),
    (
        "Tools & Equipment",
        ("tools",),
        ("Automotive Workshop Tools", "Floor Installation & Removal"),
    ),
    (
        "Events & Production Equipment",
        (),
        ("Tableware & Linen", "Rigging & Truss", "Interpretation & Tour Audio"),
    ),
    ("Food & Concession Equipment", (), ("Commercial Kitchen Equipment",)),
    (
        "Construction & Industrial Equipment",
        (),
        ("Hydraulic Maintenance Tools", "Geotextile & Site Textile Tools"),
    ),
    ("Agriculture & Landscaping", (), ("Small-Harvest Processing",)),
    ("Spaces & Studios", (), ("Retail & Pop-up Spaces",)),
    ("Music & Performance Equipment", (), ("Recording & Studio Equipment",)),
    (
        "Test & Measurement Equipment",
        ("Test and Measurement Equipment", "Test & Measurement"),
        ("Electrical Test Instruments", "Environmental Monitoring"),
    ),
)


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _lock_taxonomy_seed(bind) -> None:
    """Serialize check/insert work where the L2 table has no unique key."""
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": revision},
        )


def _find_existing_category_id(bind, categories, canonical: str, aliases: tuple[str, ...]) -> int | None:
    keys = tuple({value.casefold() for value in (canonical, *aliases)})
    rows = bind.execute(
        sa.select(categories.c.id, categories.c.name).where(
            sa.func.lower(categories.c.name).in_(tuple(value.lower() for value in keys))
        )
    ).all()
    if len(rows) > 1:
        names = ", ".join(sorted(str(row.name) for row in rows))
        raise RuntimeError(
            f"Ambiguous category aliases for {canonical!r}: {names}. "
            "Refusing to merge or rewrite taxonomy rows."
        )
    return int(rows[0].id) if rows else None


def _assert_unique_subcategories(bind, subcategories, category_id: int, canonical: str) -> None:
    duplicates = bind.execute(
        sa.select(sa.func.lower(subcategories.c.name))
        .where(subcategories.c.category_id == category_id)
        .group_by(sa.func.lower(subcategories.c.name))
        .having(sa.func.count(subcategories.c.id) > 1)
    ).scalars().all()
    if duplicates:
        raise RuntimeError(
            f"Duplicate subcategory names exist under {canonical!r}; "
            "refusing an ambiguous taxonomy migration."
        )


def _existing_subcategory_keys(bind, subcategories, category_id: int) -> set[str]:
    return {
        str(name).casefold()
        for name in bind.execute(
            sa.select(subcategories.c.name).where(subcategories.c.category_id == category_id)
        ).scalars()
    }


def _validate_snapshot() -> None:
    seen_categories: set[str] = set()
    for canonical, aliases, subcategory_names in CATEGORY_SEED:
        key = canonical.casefold()
        if not canonical or key in seen_categories:
            raise RuntimeError(f"Invalid duplicate category in migration snapshot: {canonical!r}")
        seen_categories.add(key)
        alias_keys = [alias.casefold() for alias in aliases if alias.casefold() != key]
        if len(alias_keys) != len(set(alias_keys)):
            raise RuntimeError(f"Duplicate aliases in migration snapshot: {canonical!r}")
        subcategory_keys = {name.casefold() for name in subcategory_names}
        if not subcategory_names or len(subcategory_keys) != len(subcategory_names):
            raise RuntimeError(f"Invalid subcategory snapshot: {canonical!r}")


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("research_catalog_20261005 must run online against the target database.")
    if not (_has_table("categories") and _has_table("subcategories")):
        return

    required_category_columns = {"id", "name"}
    required_subcategory_columns = {"id", "category_id", "name"}
    if not required_category_columns.issubset(_column_names("categories")):
        raise RuntimeError("categories lacks the expected taxonomy columns.")
    if not required_subcategory_columns.issubset(_column_names("subcategories")):
        raise RuntimeError("subcategories lacks the expected taxonomy columns.")

    _validate_snapshot()
    bind = op.get_bind()
    _lock_taxonomy_seed(bind)
    categories = sa.table("categories", sa.column("id", sa.Integer), sa.column("name", sa.String))
    subcategories = sa.table(
        "subcategories",
        sa.column("id", sa.Integer),
        sa.column("category_id", sa.Integer),
        sa.column("name", sa.String),
    )

    for canonical, aliases, subcategory_names in CATEGORY_SEED:
        category_id = _find_existing_category_id(bind, categories, canonical, aliases)
        if category_id is None:
            bind.execute(categories.insert().values(name=canonical))
            category_id = _find_existing_category_id(bind, categories, canonical, aliases)
        if category_id is None:
            raise RuntimeError(f"Could not create category {canonical!r}.")

        _assert_unique_subcategories(bind, subcategories, category_id, canonical)
        existing = _existing_subcategory_keys(bind, subcategories, category_id)
        for subcategory_name in subcategory_names:
            if subcategory_name.casefold() not in existing:
                bind.execute(
                    subcategories.insert().values(category_id=category_id, name=subcategory_name)
                )
                existing.add(subcategory_name.casefold())


def downgrade() -> None:
    # Forward-only: never remove taxonomy rows or alter old listings.
    return None
