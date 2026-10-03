"""apply the research taxonomy delta after the scoped production bridge

Revision ID: research_bridge_20261005
Revises: taxonomy_bridge_20261004
Create Date: 2026-10-05

Production was recorded at ``msg_attach_storage_20260927`` when the taxonomy
work began.  The normal rental-catalog lineage reaches the same data through
an unrelated Finder migration, so this small branch is the production-safe
path for a taxonomy-only release:

``msg_attach_storage_20260927 -> taxonomy_bridge_20261004 -> research_bridge_20261005``

It is an immutable L1/L2 snapshot.  It never imports the live application
catalog, never deletes or renames rows, and fails closed when an existing
parent alias or child row is ambiguous.  Third-level values remain in the
deployed central application catalog and are stored on ``items.third_level``.
"""
import os

from alembic import context, op
import sqlalchemy as sa


revision = "research_bridge_20261005"
down_revision = "taxonomy_bridge_20261004"
branch_labels = None
depends_on = None


# Keep this historical snapshot independent from the mutable runtime catalog.
# It is deliberately the same additive L1/L2 delta as
# research_catalog_20261005, so either supported Alembic lineage produces the
# same lookup-table state without reclassifying any Item.
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


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _lock_taxonomy_seed(bind) -> None:
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": revision},
        )


def _validate_snapshot() -> None:
    category_keys: set[str] = set()
    for canonical, aliases, children in CATEGORY_SEED:
        key = canonical.casefold()
        if not canonical or key in category_keys:
            raise RuntimeError(f"Invalid duplicate category in migration snapshot: {canonical!r}")
        category_keys.add(key)
        alias_keys = [alias.casefold() for alias in aliases if alias.casefold() != key]
        if len(alias_keys) != len(set(alias_keys)):
            raise RuntimeError(f"Duplicate aliases in migration snapshot: {canonical!r}")
        child_keys = {child.casefold() for child in children}
        if not children or len(child_keys) != len(children):
            raise RuntimeError(f"Invalid child snapshot: {canonical!r}")


def _find_category_id(bind, categories, canonical: str, aliases: tuple[str, ...]) -> int | None:
    keys = tuple({value.casefold() for value in (canonical, *aliases)})
    rows = bind.execute(
        sa.select(categories.c.id, categories.c.name).where(
            sa.func.lower(categories.c.name).in_(keys)
        )
    ).all()
    if len(rows) > 1:
        names = ", ".join(sorted(str(row.name) for row in rows))
        raise RuntimeError(
            f"Ambiguous category aliases for {canonical!r}: {names}. "
            "Refusing to merge or rewrite taxonomy rows."
        )
    return int(rows[0].id) if rows else None


def _assert_unique_children(bind, subcategories, category_id: int, canonical: str) -> None:
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


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("research_bridge_20261005 must run online against the target database.")

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    required_tables = {"categories", "subcategories"}
    missing_tables = required_tables - tables
    if missing_tables:
        # On the normal full-head lineage this sibling branch can be visited
        # before the ordinary rental migration creates lookup tables.  It must
        # then remain a no-op; that lineage has its own immutable research
        # seed.  The explicit production command sets strict mode, so a
        # malformed production bridge still fails before any write.
        if os.getenv("SEVOR_TAXONOMY_BRIDGE_STRICT") == "1":
            raise RuntimeError("Missing taxonomy tables: " + ", ".join(sorted(missing_tables)))
        return
    if not {"id", "name"}.issubset(_column_names("categories")):
        raise RuntimeError("categories lacks the expected taxonomy columns.")
    if not {"id", "category_id", "name"}.issubset(_column_names("subcategories")):
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

    for canonical, aliases, children in CATEGORY_SEED:
        category_id = _find_category_id(bind, categories, canonical, aliases)
        if category_id is None:
            bind.execute(categories.insert().values(name=canonical))
            category_id = _find_category_id(bind, categories, canonical, aliases)
        if category_id is None:
            raise RuntimeError(f"Could not create category {canonical!r}.")

        _assert_unique_children(bind, subcategories, category_id, canonical)
        existing = {
            str(name).casefold()
            for name in bind.execute(
                sa.select(subcategories.c.name).where(subcategories.c.category_id == category_id)
            ).scalars()
        }
        for child in children:
            if child.casefold() not in existing:
                bind.execute(subcategories.insert().values(category_id=category_id, name=child))
                existing.add(child.casefold())


def downgrade() -> None:
    # Forward-only: preserving existing taxonomy records is the safe behavior.
    return None
