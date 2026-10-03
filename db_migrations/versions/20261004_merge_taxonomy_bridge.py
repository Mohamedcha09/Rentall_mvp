"""merge the normal catalog lineage and the production taxonomy bridge

Revision ID: merge_taxonomy_20261004
Revises: rental_catalog_20261004, taxonomy_bridge_20261004
Create Date: 2026-10-04

The bridge is intentionally run by explicit revision from the old production
base.  This merge records one future repository head without stamping or
pretending that the unrelated Finder lineage was applied.
"""


revision = "merge_taxonomy_20261004"
down_revision = ("rental_catalog_20261004", "taxonomy_bridge_20261004")
branch_labels = None
depends_on = None


def upgrade() -> None:
    return None


def downgrade() -> None:
    return None
