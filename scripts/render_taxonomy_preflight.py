"""Read-only preflight for the scoped SEVOR production taxonomy bridge.

This script intentionally does not import ``app.database`` because that module
has legacy startup hooks.  It never prints a connection URL or secret and it
opens PostgreSQL in a read-only transaction.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

# Allow ``python scripts/render_taxonomy_preflight.py`` from the repository
# root without relying on a shell-specific PYTHONPATH expansion.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.catalog_taxonomy import DIGITAL_ACCOUNTS_CATEGORY, DIGITAL_ACCOUNTS_SERVICES
from app.rental_catalog import RENTAL_CATEGORIES


def _database_url() -> tuple[str | None, str | None]:
    for variable in ("DATABASE_URL", "DATABASE_URL_FULL", "DATABASE_URI"):
        value = os.getenv(variable)
        if value:
            return value, variable
    return None, None


def _normalized_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _catalog_expectations() -> dict[str, tuple[set[str], set[str]]]:
    """Return canonical category -> (accepted parent spellings, required L2)."""
    result: dict[str, tuple[set[str], set[str]]] = {}
    for category in RENTAL_CATEGORIES:
        result[category.value.canonical] = (
            {category.value.canonical.casefold(), *(alias.casefold() for alias in category.aliases)},
            {branch.value.canonical for branch in category.branches},
        )
    result[DIGITAL_ACCOUNTS_CATEGORY] = (
        {DIGITAL_ACCOUNTS_CATEGORY.casefold()},
        set(DIGITAL_ACCOUNTS_SERVICES),
    )
    return result


def _catalog_result(connection) -> tuple[list[str], list[str]]:
    category_rows = connection.execute(text("SELECT id, name FROM categories ORDER BY id")).mappings().all()
    subcategory_rows = connection.execute(
        text("SELECT category_id, name FROM subcategories ORDER BY category_id, id")
    ).mappings().all()
    parents_by_folded_name: dict[str, list[int]] = defaultdict(list)
    for row in category_rows:
        parents_by_folded_name[str(row["name"]).casefold()].append(int(row["id"]))
    children_by_parent: dict[int, list[str]] = defaultdict(list)
    for row in subcategory_rows:
        children_by_parent[int(row["category_id"])].append(str(row["name"]))

    missing: list[str] = []
    ambiguous: list[str] = []
    for canonical, (accepted_names, required_children) in _catalog_expectations().items():
        ids = {
            parent_id
            for accepted_name in accepted_names
            for parent_id in parents_by_folded_name.get(accepted_name, [])
        }
        if len(ids) != 1:
            (ambiguous if ids else missing).append(
                f"L1 {canonical}" if not ids else f"L1 {canonical} has {len(ids)} alias matches"
            )
            continue
        parent_id = next(iter(ids))
        present_children = {name.casefold() for name in children_by_parent[parent_id]}
        for child in sorted(required_children):
            if child.casefold() not in present_children:
                missing.append(f"L2 {canonical} -> {child}")
        child_counts: dict[str, int] = defaultdict(int)
        for child in children_by_parent[parent_id]:
            child_counts[child.casefold()] += 1
        for child, count in child_counts.items():
            if count > 1:
                ambiguous.append(f"L2 {canonical} -> {child} has {count} rows")
    return missing, ambiguous


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-revision",
        help="Fail unless alembic_version contains exactly this revision.",
    )
    parser.add_argument(
        "--require-catalog",
        action="store_true",
        help="Fail unless all configured L1/L2 lookup rows are present exactly once.",
    )
    args = parser.parse_args()

    raw_url, source = _database_url()
    if not raw_url:
        print("DATABASE_URL_NOT_CONFIGURED")
        return 2
    engine = create_engine(_normalized_url(raw_url), pool_pre_ping=True, future=True)
    if engine.url.get_backend_name() != "postgresql":
        print(f"DATABASE_BACKEND={engine.url.get_backend_name()}")
        print("EXPECTED_BACKEND=postgresql")
        return 2

    print(f"DATABASE_URL_SOURCE={source}")
    print("DATABASE_BACKEND=postgresql")
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            print("TABLES=" + ",".join(sorted(table for table in ("items", "categories", "subcategories", "alembic_version") if table in tables)))

            if "alembic_version" not in tables:
                print("ALEMBIC_REVISION=MISSING")
                return 3
            revisions = [
                str(row["version_num"])
                for row in connection.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")).mappings()
            ]
            print("ALEMBIC_REVISION=" + ",".join(revisions))
            if args.require_revision and revisions != [args.require_revision]:
                print("REVISION_REQUIREMENT_FAILED")
                return 3

            required_tables = {"items", "categories", "subcategories"}
            missing_tables = required_tables - tables
            if missing_tables:
                print("MISSING_TABLES=" + ",".join(sorted(missing_tables)))
                return 4
            item_columns = {column["name"] for column in inspector.get_columns("items")}
            category_columns = {column["name"] for column in inspector.get_columns("categories")}
            subcategory_columns = {column["name"] for column in inspector.get_columns("subcategories")}
            print("ITEM_TAXONOMY_COLUMNS=" + ",".join(
                name for name in ("category", "subcategory", "third_level", "custom_third_level") if name in item_columns
            ))
            missing_lookup_columns = (
                ({"id", "name"} - category_columns)
                | ({"id", "category_id", "name"} - subcategory_columns)
            )
            if missing_lookup_columns:
                print("MISSING_LOOKUP_COLUMNS=" + ",".join(sorted(missing_lookup_columns)))
                return 4
            missing_item_columns = {
                "category", "subcategory", "third_level", "custom_third_level"
            } - item_columns
            if missing_item_columns:
                print("MISSING_ITEM_TAXONOMY_COLUMNS=" + ",".join(sorted(missing_item_columns)))
                # Missing L2/L3 columns is the expected *pre-bridge* state.
                # It becomes an error only for the post-write catalog check.
                if args.require_catalog:
                    return 4

            category_count = connection.execute(text("SELECT COUNT(*) FROM categories")).scalar_one()
            subcategory_count = connection.execute(text("SELECT COUNT(*) FROM subcategories")).scalar_one()
            print(f"LOOKUP_COUNTS=L1:{category_count};L2:{subcategory_count}")
            missing, ambiguous = _catalog_result(connection)
            print(f"CATALOG_MISSING={len(missing)}")
            print(f"CATALOG_AMBIGUOUS={len(ambiguous)}")
            for value in missing[:20]:
                print("MISSING=" + value)
            for value in ambiguous[:20]:
                print("AMBIGUOUS=" + value)
            if args.require_catalog and (missing or ambiguous):
                return 5
    except Exception as exc:
        # Exception text may contain environment/provider details, so report
        # only the type rather than forwarding a possible connection string.
        print("PREFLIGHT_FAILED=" + type(exc).__name__)
        return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
