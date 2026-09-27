"""add private support attachments and message receipts

Revision ID: support_media_receipts_20260927
Revises: add_items_website_url_20260923
Create Date: 2026-09-27
"""

from alembic import context, op
import sqlalchemy as sa


revision = "support_media_receipts_20260927"
down_revision = "add_items_website_url_20260923"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _has_table("support_attachments"):
        op.create_table(
            "support_attachments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=False),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("support_messages.id"), nullable=False),
            sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("original_name", sa.String(length=180), nullable=False),
            sa.Column("stored_name", sa.String(length=96), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("stored_name", name="uq_support_attachments_stored_name"),
        )
        op.create_index("ix_support_attachments_ticket_id", "support_attachments", ["ticket_id"])
        op.create_index("ix_support_attachments_message_id", "support_attachments", ["message_id"])
        op.create_index("ix_support_attachments_uploader_id", "support_attachments", ["uploader_id"])
        op.create_index("ix_support_attachments_created_at", "support_attachments", ["created_at"])

    if not _has_table("support_message_receipts"):
        op.create_table(
            "support_message_receipts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("support_messages.id"), nullable=False),
            sa.Column("reader_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("read_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "message_id", "reader_id", name="ux_support_message_receipts_message_reader"
            ),
        )
        op.create_index("ix_support_message_receipts_message_id", "support_message_receipts", ["message_id"])
        op.create_index("ix_support_message_receipts_reader_id", "support_message_receipts", ["reader_id"])
        op.create_index("ix_support_message_receipts_read_at", "support_message_receipts", ["read_at"])


def downgrade():
    if _has_table("support_message_receipts"):
        op.drop_table("support_message_receipts")
    if _has_table("support_attachments"):
        op.drop_table("support_attachments")
