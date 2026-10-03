"""merge the normal and production-safe research taxonomy lineages

Revision ID: merge_research_taxonomy_20261005
Revises: research_catalog_20261005, research_bridge_20261005
Create Date: 2026-10-05

The normal development lineage reaches the research lookup seed after the
Finder branch.  Production can instead reach the same lookup state through
the scoped taxonomy bridge.  This no-op merge keeps one future repository
head; it does not mark either branch as applied early.
"""


revision = "merge_research_taxonomy_20261005"
down_revision = ("research_catalog_20261005", "research_bridge_20261005")
branch_labels = None
depends_on = None


def upgrade() -> None:
    return None


def downgrade() -> None:
    return None
