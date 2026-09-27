"""persist direct-message attachment storage metadata

Revision ID: message_attachment_storage_20260927
Revises: direct_message_media_20260927
Create Date: 2026-09-27
"""

from alembic import context, op
import sqlalchemy as sa


revision = "message_attachment_storage_20260927"
down_revision = "direct_message_media_20260927"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table: str) -> set[str]:
    if context.is_offline_mode() or not _has_table(table):
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if not _has_table("message_attachments"):
        return

    columns = _columns("message_attachments")
    additions = (
        ("storage_backend", sa.String(length=16)),
        ("storage_key", sa.String(length=255)),
        ("storage_resource_type", sa.String(length=16)),
        ("storage_delivery_type", sa.String(length=16)),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column("message_attachments", sa.Column(name, column_type, nullable=True))

    # New records always receive an explicit backend.  Existing rows are
    # backfilled only enough to preserve their current semantics: normal UUID
    # rows remain local, while the short-lived prior Cloudinary format remains
    # readable through its compatibility path.
    op.execute(
        """
        UPDATE message_attachments
        SET storage_backend = CASE
            WHEN stored_name LIKE 'cld1:%' THEN 'cloudinary'
            ELSE 'local'
        END
        WHERE storage_backend IS NULL OR storage_backend = ''
        """
    )
    op.execute(
        """
        UPDATE message_attachments
        SET storage_key = stored_name
        WHERE storage_backend = 'local'
          AND (storage_key IS NULL OR storage_key = '')
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_message_attachments_storage_backend "
        "ON message_attachments(storage_backend)"
    )


def downgrade():
    if not _has_table("message_attachments"):
        return
    op.execute("DROP INDEX IF EXISTS ix_message_attachments_storage_backend")
    columns = _columns("message_attachments")
    for name in ("storage_delivery_type", "storage_resource_type", "storage_key", "storage_backend"):
        if name in columns:
            op.drop_column("message_attachments", name)
