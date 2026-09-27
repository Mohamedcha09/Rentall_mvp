"""add private direct-message media and idempotency

Revision ID: direct_message_media_20260927
Revises: support_media_receipts_20260927
Create Date: 2026-09-27
"""

from alembic import context, op
import sqlalchemy as sa


revision = "direct_message_media_20260927"
down_revision = "support_media_receipts_20260927"
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
    if "client_message_id" not in _columns("messages"):
        op.add_column("messages", sa.Column("client_message_id", sa.String(length=72), nullable=True))

    if not _has_table("message_attachments"):
        op.create_table(
            "message_attachments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("thread_id", sa.Integer(), sa.ForeignKey("message_threads.id"), nullable=False),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=False),
            sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False, server_default="file"),
            sa.Column("original_name", sa.String(length=180), nullable=False),
            sa.Column("stored_name", sa.String(length=96), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("stored_name", name="uq_message_attachments_stored_name"),
        )
        op.create_index("ix_message_attachments_thread_id", "message_attachments", ["thread_id"])
        op.create_index("ix_message_attachments_message_id", "message_attachments", ["message_id"])
        op.create_index("ix_message_attachments_uploader_id", "message_attachments", ["uploader_id"])
        op.create_index("ix_message_attachments_created_at", "message_attachments", ["created_at"])

    # A partial unique index deliberately permits legacy rows with no client
    # id while making browser retries idempotent for a participant/thread.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_thread_sender_client_message "
        "ON messages(thread_id, sender_id, client_message_id) "
        "WHERE client_message_id IS NOT NULL"
    )
    if _has_table("online_sessions"):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_online_sessions_user_last_seen "
            "ON online_sessions(user_id, last_seen)"
        )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ux_messages_thread_sender_client_message")
    op.execute("DROP INDEX IF EXISTS ix_online_sessions_user_last_seen")
    if _has_table("message_attachments"):
        op.drop_table("message_attachments")
    if "client_message_id" in _columns("messages"):
        op.drop_column("messages", "client_message_id")
