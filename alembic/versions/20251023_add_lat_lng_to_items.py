"""add latitude/longitude to items

Revision ID: add_lat_lng_to_items_20251023
Revises:
Create Date: 2025-10-23
"""
from alembic import op
import sqlalchemy as sa

revision = "add_lat_lng_to_items_20251023"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # double precision في PostgreSQL
    op.add_column("items", sa.Column("latitude", sa.Float(precision=53), nullable=True))
    op.add_column("items", sa.Column("longitude", sa.Float(precision=53), nullable=True))

def downgrade():
    op.drop_column("items", "longitude")
    op.drop_column("items", "latitude")