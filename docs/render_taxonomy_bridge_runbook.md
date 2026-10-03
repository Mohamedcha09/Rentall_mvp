# SEVOR production taxonomy bridge

This runbook is intentionally limited to the taxonomy persistence problem.
It does not deploy Finder, create listings, delete data, or run a general
Alembic upgrade.

## Why a database command alone is not enough

`items.third_level` is not a lookup-table value in this application.  Level 3
is defined by the deployed central catalog code.  The deployed source must
therefore include the catalog/Create/Edit changes, `app/database.py`, and the
two bridge migration files before the database write is performed.

The app now accepts `DATABASE_URL`, `DATABASE_URL_FULL`, or `DATABASE_URI`.
On a Render runtime it refuses to fall back silently to local SQLite when all
three are absent.

## Required safety conditions

1. Rotate the database credential that was previously exposed in chat, then
   update the linked Web Service environment value in Render. Do not paste it
   into the Shell or this document.
2. Create and wait for a Recover/Backup export or snapshot for `sevor-db`.
   If no recoverable backup is available, stop before the write.
3. Deploy the reviewed source containing:
   - `app/database.py`
   - `app/rental_catalog.py` and `app/catalog_taxonomy.py`
   - `app/items.py` and the Create/Edit templates
   - `db_migrations/versions/20261004_taxonomy_production_bridge.py`
   - `db_migrations/versions/20261004_merge_taxonomy_bridge.py`
   - `scripts/render_taxonomy_preflight.py`

## Render Web Shell commands

Run these from the deployed Web Service Shell, in order. They never print a
connection string.

```bash
cd ~/project/src
test -f db_migrations/versions/20261004_taxonomy_production_bridge.py
PYTHONPATH="$PWD" python scripts/render_taxonomy_preflight.py --require-revision msg_attach_storage_20260927
```

The preflight must print `DATABASE_BACKEND=postgresql` and the required base
revision. Before the bridge, `MISSING_ITEM_TAXONOMY_COLUMNS` for the new
second/third-level fields is expected. Stop if it reports a different
revision, a missing lookup table/lookup column, or a different backend.

After the backup and successful preflight, run exactly this scoped migration:

```bash
SEVOR_TAXONOMY_BRIDGE_STRICT=1 PYTHONPATH="$PWD" alembic upgrade taxonomy_bridge_20261004
```

Then verify without writing:

```bash
PYTHONPATH="$PWD" python scripts/render_taxonomy_preflight.py --require-revision taxonomy_bridge_20261004 --require-catalog
PYTHONPATH="$PWD" alembic current
PYTHONPATH="$PWD" alembic heads
```

Expected post-write facts:

- `alembic current`: `taxonomy_bridge_20261004`
- repository `heads`: `merge_taxonomy_20261004`
- 21 resolved Level-1 parents and all 121 Level-2 rows
- `items.category`, `items.subcategory`, `items.third_level`, and
  `items.custom_third_level` exist

The differing `current`/`heads` values are intentional: the bridge avoids the
unrelated Finder migration. Do **not** use `alembic upgrade head` or
`alembic stamp` as a shortcut. A later separately-approved Finder rollout can
reconcile the other lineage through the merge revision.

Finally, restart only the existing Web Service so SQLAlchemy reloads the three
new Item columns, then verify Create Listing and Explore without submitting a
fake production listing.
