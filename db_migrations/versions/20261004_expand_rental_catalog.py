"""seed the additive rental category and subcategory catalog

Revision ID: rental_catalog_20261004
Revises: digital_catalog_20261003
Create Date: 2026-10-04

This migration intentionally contains an immutable L1/L2 snapshot.  It does
not import ``app.rental_catalog``: a historical migration must retain the same
meaning when the application catalog evolves later.  Third-level choices are
defined in the application catalog because the current schema has no separate
third-level lookup table.

The migration only inserts missing lookup rows.  It never deletes, renames, or
reclassifies an existing category, subcategory, or Item.  Legacy category names
listed as aliases are accepted as an existing parent so older listings remain
valid; ambiguous canonical/alias matches stop the transaction rather than
silently merging data.
"""
from alembic import context, op
import sqlalchemy as sa


revision = "rental_catalog_20261004"
down_revision = "digital_catalog_20261003"
branch_labels = None
depends_on = None


# Immutable L1/L2 snapshot from the 2026-10-04 expanded rental catalog.  Keep
# this data local to the revision; do not replace it with an application import.
CATEGORY_SEED = (
    (
        "Vehicles",
        ("vehicle",),
        (
            "Cars",
            "Buses",
            "Trucks & Vans",
            "Trailers & RVs",
            "Bicycles & Micro-mobility",
            "Motorcycles & Scooters",
        ),
    ),
    (
        "Housing & Stays",
        ("housing",),
        (
            "Apartments & Homes",
            "Vacation Properties",
            "Rooms & Shared Stays",
            "Parking & Storage",
        ),
    ),
    (
        "Electronics",
        ("electronics",),
        (
            "Computers & Tablets",
            "Cameras & Video",
            "Networking & Communications",
            "Office Tech",
            "Gaming & VR",
        ),
    ),
    (
        "Furniture",
        ("furniture",),
        (
            "Home Furniture",
            "Office Furniture",
            "Event Furniture",
            "Appliances",
            "Rugs & Decor",
        ),
    ),
    (
        "Clothing & Costumes",
        ("clothing",),
        (
            "Formal & Bridal",
            "Costumes & Theatrical",
            "Outdoor & Specialty",
            "Accessories",
        ),
    ),
    (
        "Tools & Equipment",
        ("tools",),
        (
            "Power Tools",
            "Hand Tools",
            "Plumbing & Pipe Tools",
            "Electrical & Testing Tools",
            "Cleaning & Restoration Equipment",
            "Surveying & Inspection",
        ),
    ),
    (
        "Baby & Kids",
        (),
        (
            "Travel & Safety",
            "Nursery & Sleep",
            "Toys & Play",
            "Party & Event Gear",
        ),
    ),
    (
        "Sports & Outdoors",
        ("sports", "Sports Equipment"),
        (
            "Camping & Outdoors",
            "Winter Sports",
            "Water Sports",
            "Fitness Equipment",
            "Team Sports",
            "Fishing Equipment",
        ),
    ),
    (
        "Books & Learning",
        ("books",),
        (
            "Books",
            "Classroom Equipment",
            "Lab & Science Kits",
            "Training & Presentation",
        ),
    ),
    (
        "Events & Production Equipment",
        (),
        (
            "Tents & Canopies",
            "Staging & Flooring",
            "Audio Equipment",
            "Lighting Equipment",
            "Video & Displays",
            "Photo Booths & Signage",
            "Crowd Control & Safety",
            "Event Furniture",
        ),
    ),
    (
        "Food & Concession Equipment",
        (),
        (
            "Popcorn Equipment",
            "Hot Dog Equipment",
            "Donut Equipment",
            "Frozen & Dessert Equipment",
            "Cooking Equipment",
            "Serving & Beverage Equipment",
            "Mobile Food Units",
            "Sanitation & Dishwashing",
        ),
    ),
    (
        "Construction & Industrial Equipment",
        (),
        (
            "Earthmoving",
            "Aerial Access",
            "Concrete & Masonry",
            "Compaction & Paving",
            "Air & Pneumatic",
            "Welding & Fabrication",
            "Trench & Shoring",
        ),
    ),
    (
        "Agriculture & Landscaping",
        (),
        (
            "Tractors & Implements",
            "Lawn & Garden",
            "Forestry & Tree Care",
            "Irrigation & Water",
            "Livestock & Farm Handling",
        ),
    ),
    (
        "Warehousing & Logistics",
        (),
        (
            "Forklifts & Telehandlers",
            "Pallet & Manual Handling",
            "Storage & Containers",
            "Loading & Dock",
            "Packaging & Labeling",
        ),
    ),
    (
        "Temporary Infrastructure & Site Services",
        (),
        (
            "Power Generation",
            "Climate Control",
            "Drying & Air Quality",
            "Sanitation",
            "Fencing & Traffic Control",
            "Mobile Offices & Structures",
            "Pumps & Water Management",
        ),
    ),
    (
        "Marine & Watercraft",
        (),
        ("Boats", "Personal Watercraft", "Marine Gear"),
    ),
    (
        "Spaces & Studios",
        (),
        (
            "Event Venues",
            "Studios",
            "Meeting & Workspaces",
            "Workshops & Maker Spaces",
            "Commercial Kitchens",
        ),
    ),
    (
        "Retail & Vending Equipment",
        (),
        (
            "Display & Merchandising",
            "POS & Checkout",
            "Kiosks & Booths",
            "Vending & Refrigerated Merchandising",
        ),
    ),
    (
        "Music & Performance Equipment",
        (),
        (
            "Musical Instruments",
            "DJ Equipment",
            "Amplification & Backline",
            "Rehearsal & Performance Gear",
        ),
    ),
    (
        "Hobbies & Creative Equipment",
        (),
        (
            "Printing & Fabrication",
            "Sewing & Textile",
            "Arts & Crafts",
            "Games & Recreation",
        ),
    ),
)


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _column_names(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _lock_taxonomy_seed(bind) -> None:
    """Serialize check/insert work where subcategories have no DB unique key."""
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": revision},
        )


def _find_existing_category_id(bind, categories, canonical: str, aliases: tuple[str, ...]) -> int | None:
    candidate_keys = tuple({name.casefold() for name in (canonical, *aliases)})
    rows = bind.execute(
        sa.select(categories.c.id, categories.c.name).where(
            sa.func.lower(categories.c.name).in_(tuple(key.lower() for key in candidate_keys))
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
    category_keys: set[str] = set()
    for canonical, aliases, subcategory_names in CATEGORY_SEED:
        category_key = canonical.casefold()
        if not canonical or category_key in category_keys:
            raise RuntimeError(f"Invalid duplicate category in migration snapshot: {canonical!r}")
        category_keys.add(category_key)
        # A lower-case legacy spelling such as ``electronics`` is compatible
        # with the canonical ``Electronics`` through the case-insensitive
        # lookup.  It is useful documentation in this immutable snapshot and
        # is not an ambiguous second parent.  Two distinct aliases that fold
        # to each other remain unsafe.
        alias_keys = [alias.casefold() for alias in aliases if alias.casefold() != category_key]
        if len(set(alias_keys)) != len(alias_keys):
            raise RuntimeError(f"Duplicate aliases in migration snapshot: {canonical!r}")
        subcategory_keys = {name.casefold() for name in subcategory_names}
        if not subcategory_names or len(subcategory_keys) != len(subcategory_names):
            raise RuntimeError(f"Invalid subcategory snapshot: {canonical!r}")


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("rental_catalog_20261004 must run online against the target database.")
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
                    subcategories.insert().values(
                        category_id=category_id,
                        name=subcategory_name,
                    )
                )
                existing.add(subcategory_name.casefold())


def downgrade() -> None:
    # Forward-only: rolling back must not remove lookup records or alter items.
    return None
