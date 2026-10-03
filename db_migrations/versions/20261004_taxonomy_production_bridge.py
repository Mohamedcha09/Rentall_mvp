"""apply the taxonomy schema and catalog directly after the production base

Revision ID: taxonomy_bridge_20261004
Revises: msg_attach_storage_20260927
Create Date: 2026-10-04

The production database reported this base revision while the normal taxonomy
lineage is downstream of an unrelated Finder migration.  This deliberately
scoped bridge is the only migration that may be targeted from that base for a
taxonomy-only release.  It never creates Finder objects, never deletes data,
and never rewrites ordinary listings.

It is online-only, transactional through Alembic, and fails closed if lookup
parents or siblings are ambiguous.  Third-level values remain in the deployed
application catalog; the current schema has no third-level lookup table.
"""
import os

from alembic import context, op
import sqlalchemy as sa


revision = "taxonomy_bridge_20261004"
down_revision = "msg_attach_storage_20260927"
branch_labels = None
depends_on = None


# Immutable snapshot.  Do not import application catalog modules from this
# historical migration: future catalog edits must not alter a past upgrade.
DIGITAL_CATEGORY = "Digital Accounts"
DIGITAL_TYPES = (
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
    "General Subscriptions",
    "Other",
)

RENTAL_CATEGORY_SEED = (
    ("Vehicles", ("vehicle",), ("Cars", "Buses", "Trucks & Vans", "Trailers & RVs", "Bicycles & Micro-mobility", "Motorcycles & Scooters")),
    ("Housing & Stays", ("housing",), ("Apartments & Homes", "Vacation Properties", "Rooms & Shared Stays", "Parking & Storage")),
    ("Electronics", ("electronics",), ("Computers & Tablets", "Cameras & Video", "Networking & Communications", "Office Tech", "Gaming & VR")),
    ("Furniture", ("furniture",), ("Home Furniture", "Office Furniture", "Event Furniture", "Appliances", "Rugs & Decor")),
    ("Clothing & Costumes", ("clothing",), ("Formal & Bridal", "Costumes & Theatrical", "Outdoor & Specialty", "Accessories")),
    ("Tools & Equipment", ("tools",), ("Power Tools", "Hand Tools", "Plumbing & Pipe Tools", "Electrical & Testing Tools", "Cleaning & Restoration Equipment", "Surveying & Inspection")),
    ("Baby & Kids", (), ("Travel & Safety", "Nursery & Sleep", "Toys & Play", "Party & Event Gear")),
    ("Sports & Outdoors", ("sports", "Sports Equipment"), ("Camping & Outdoors", "Winter Sports", "Water Sports", "Fitness Equipment", "Team Sports", "Fishing Equipment")),
    ("Books & Learning", ("books",), ("Books", "Classroom Equipment", "Lab & Science Kits", "Training & Presentation")),
    ("Events & Production Equipment", (), ("Tents & Canopies", "Staging & Flooring", "Audio Equipment", "Lighting Equipment", "Video & Displays", "Photo Booths & Signage", "Crowd Control & Safety", "Event Furniture")),
    ("Food & Concession Equipment", (), ("Popcorn Equipment", "Hot Dog Equipment", "Donut Equipment", "Frozen & Dessert Equipment", "Cooking Equipment", "Serving & Beverage Equipment", "Mobile Food Units", "Sanitation & Dishwashing")),
    ("Construction & Industrial Equipment", (), ("Earthmoving", "Aerial Access", "Concrete & Masonry", "Compaction & Paving", "Air & Pneumatic", "Welding & Fabrication", "Trench & Shoring")),
    ("Agriculture & Landscaping", (), ("Tractors & Implements", "Lawn & Garden", "Forestry & Tree Care", "Irrigation & Water", "Livestock & Farm Handling")),
    ("Warehousing & Logistics", (), ("Forklifts & Telehandlers", "Pallet & Manual Handling", "Storage & Containers", "Loading & Dock", "Packaging & Labeling")),
    ("Temporary Infrastructure & Site Services", (), ("Power Generation", "Climate Control", "Drying & Air Quality", "Sanitation", "Fencing & Traffic Control", "Mobile Offices & Structures", "Pumps & Water Management")),
    ("Marine & Watercraft", (), ("Boats", "Personal Watercraft", "Marine Gear")),
    ("Spaces & Studios", (), ("Event Venues", "Studios", "Meeting & Workspaces", "Workshops & Maker Spaces", "Commercial Kitchens")),
    ("Retail & Vending Equipment", (), ("Display & Merchandising", "POS & Checkout", "Kiosks & Booths", "Vending & Refrigerated Merchandising")),
    ("Music & Performance Equipment", (), ("Musical Instruments", "DJ Equipment", "Amplification & Backline", "Rehearsal & Performance Gear")),
    ("Hobbies & Creative Equipment", (), ("Printing & Fabrication", "Sewing & Textile", "Arts & Crafts", "Games & Recreation")),
)

LEGACY_DIGITAL_SERVICE_RENAMES = (
    ("Movies & Streaming", "BBC-related paid services", "BBC-related paid services where available"),
    ("AI Tools", "Character.AI", "Character.AI paid plans"),
    ("Regional TV & Entertainment", "ZEE5", "Zee5"),
)


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _lock(bind) -> None:
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": revision})


def _strict_mode() -> bool:
    """Make the explicit production command fail closed on schema surprises."""
    return os.getenv("SEVOR_TAXONOMY_BRIDGE_STRICT") == "1"


def _skip_or_raise(message: str) -> bool:
    if _strict_mode():
        raise RuntimeError(message)
    return False


def _item_columns_or_none() -> set[str] | None:
    if not _has_table("items"):
        _skip_or_raise("Taxonomy bridge requires the items table.")
        return None
    item_columns = _columns("items")
    if "category" not in item_columns:
        _skip_or_raise("items.category is required for the taxonomy bridge.")
        return None
    return item_columns


def _lookup_schema_ready() -> bool:
    required_tables = {"categories", "subcategories"}
    missing_tables = required_tables - set(sa.inspect(op.get_bind()).get_table_names())
    if missing_tables:
        return _skip_or_raise(
            f"Taxonomy bridge requires tables: {', '.join(sorted(missing_tables))}"
        )
    if not {"id", "name"}.issubset(_columns("categories")):
        return _skip_or_raise("categories lacks required id/name columns.")
    if not {"id", "category_id", "name"}.issubset(_columns("subcategories")):
        return _skip_or_raise("subcategories lacks required id/category_id/name columns.")
    return True


def _find_or_create_parent(bind, categories, canonical: str, aliases: tuple[str, ...]) -> int:
    candidate_names = tuple({str(value).casefold() for value in (canonical, *aliases) if str(value).strip()})
    rows = bind.execute(
        sa.select(categories.c.id, categories.c.name).where(
            sa.func.lower(categories.c.name).in_(candidate_names)
        )
    ).all()
    if len(rows) > 1:
        labels = ", ".join(sorted(str(row[1]) for row in rows))
        raise RuntimeError(
            f"Ambiguous category aliases for {canonical!r}: {labels}. "
            "No taxonomy rows were merged."
        )
    if rows:
        return int(rows[0][0])
    bind.execute(categories.insert().values(name=canonical))
    row = bind.execute(
        sa.select(categories.c.id).where(categories.c.name == canonical)
    ).scalar_one_or_none()
    if row is None:
        raise RuntimeError(f"Could not create category {canonical!r}.")
    return int(row)


def _assert_unique_children(bind, subcategories, category_id: int, parent_name: str) -> None:
    duplicates = bind.execute(
        sa.select(sa.func.lower(subcategories.c.name))
        .where(subcategories.c.category_id == category_id)
        .group_by(sa.func.lower(subcategories.c.name))
        .having(sa.func.count(subcategories.c.id) > 1)
    ).scalars().all()
    if duplicates:
        raise RuntimeError(
            f"Duplicate subcategory names under {parent_name!r}; bridge aborted without merging rows."
        )


def _insert_missing_children(bind, subcategories, category_id: int, names: tuple[str, ...]) -> None:
    existing = {
        str(value).casefold()
        for value in bind.execute(
            sa.select(subcategories.c.name).where(subcategories.c.category_id == category_id)
        ).scalars()
    }
    for name in names:
        if name.casefold() not in existing:
            bind.execute(subcategories.insert().values(category_id=category_id, name=name))
            existing.add(name.casefold())


def _correct_digital_legacy_values(bind, subcategories, items, category_id: int, item_columns: set[str]) -> None:
    names = set(
        bind.execute(
            sa.select(subcategories.c.name).where(subcategories.c.category_id == category_id)
        ).scalars()
    )
    general_legacy = "General"
    general_canonical = "General Subscriptions"
    if general_legacy in names and general_canonical in names:
        raise RuntimeError(
            "Both Digital Accounts / General and General Subscriptions exist; "
            "bridge refuses to merge them automatically."
        )
    if general_legacy in names:
        if {"category", "subcategory"}.issubset(item_columns):
            bind.execute(
                items.update()
                .where(
                    items.c.category == DIGITAL_CATEGORY,
                    items.c.subcategory == general_legacy,
                )
                .values(subcategory=general_canonical)
            )
        bind.execute(
            subcategories.update()
            .where(
                subcategories.c.category_id == category_id,
                subcategories.c.name == general_legacy,
            )
            .values(name=general_canonical)
        )

    if {"category", "subcategory", "third_level"}.issubset(item_columns):
        for subcategory, legacy_value, canonical_value in LEGACY_DIGITAL_SERVICE_RENAMES:
            bind.execute(
                items.update()
                .where(
                    items.c.category == DIGITAL_CATEGORY,
                    items.c.subcategory == subcategory,
                    items.c.third_level == legacy_value,
                )
                .values(third_level=canonical_value)
            )


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("taxonomy_bridge_20261004 must run online against the target database.")

    item_columns = _item_columns_or_none()
    if item_columns is None:
        return
    bind = op.get_bind()
    _lock(bind)

    if "subcategory" not in item_columns:
        op.add_column("items", sa.Column("subcategory", sa.String(length=120), nullable=True))
    if "third_level" not in item_columns:
        op.add_column("items", sa.Column("third_level", sa.String(length=160), nullable=True))
    if "custom_third_level" not in item_columns:
        op.add_column("items", sa.Column("custom_third_level", sa.String(length=200), nullable=True))
    item_columns = _columns("items")
    if {"category", "subcategory", "third_level"}.issubset(item_columns):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_items_category_subcategory_third_level "
            "ON items (category, subcategory, third_level)"
        )

    # The normal history can reach this bridge while testing or upgrading a
    # deliberately minimal old schema without lookup tables.  It must remain
    # additive in that route.  The explicit production command sets strict
    # mode and therefore aborts rather than silently skipping its catalog.
    if not _lookup_schema_ready():
        return

    categories = sa.table(
        "categories",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
    )
    subcategories = sa.table(
        "subcategories",
        sa.column("id", sa.Integer),
        sa.column("category_id", sa.Integer),
        sa.column("name", sa.String),
    )
    items = sa.table(
        "items",
        sa.column("category", sa.String),
        sa.column("subcategory", sa.String),
        sa.column("third_level", sa.String),
    )

    for canonical, aliases, child_names in RENTAL_CATEGORY_SEED:
        category_id = _find_or_create_parent(bind, categories, canonical, aliases)
        _assert_unique_children(bind, subcategories, category_id, canonical)
        _insert_missing_children(bind, subcategories, category_id, child_names)

    digital_category_id = _find_or_create_parent(bind, categories, DIGITAL_CATEGORY, ())
    _assert_unique_children(bind, subcategories, digital_category_id, DIGITAL_CATEGORY)
    _correct_digital_legacy_values(
        bind, subcategories, items, digital_category_id, item_columns
    )
    _assert_unique_children(bind, subcategories, digital_category_id, DIGITAL_CATEGORY)
    _insert_missing_children(bind, subcategories, digital_category_id, DIGITAL_TYPES)


def downgrade() -> None:
    # Forward-only: lookup rows can be referenced by production listings.
    return None
