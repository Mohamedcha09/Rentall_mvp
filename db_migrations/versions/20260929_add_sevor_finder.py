"""add isolated Sevor Finder conversations and listing index

Revision ID: sevor_finder_20260929
Revises: msg_attach_storage_20260927
Create Date: 2026-09-29

The search index is derived from public Item data.  This migration creates no
listing content and never changes visibility, prices, or support conversations.
After upgrade, run the documented Finder rebuild command once before relying on
index coverage metrics in production.
"""

from alembic import context, op
import sqlalchemy as sa


revision = "sevor_finder_20260929"
down_revision = "msg_attach_storage_20260927"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("finder_conversations"):
        op.create_table(
            "finder_conversations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
            sa.Column("active_revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("context_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_finder_conversations_user_id", "finder_conversations", ["user_id"])
        op.create_index("ix_finder_conversations_status", "finder_conversations", ["status"])
        op.create_index("ix_finder_conversations_created_at", "finder_conversations", ["created_at"])
        op.create_index("ix_finder_conversations_updated_at", "finder_conversations", ["updated_at"])

    if not _has_table("finder_messages"):
        op.create_table(
            "finder_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("finder_conversations.id"), nullable=False),
            sa.Column("sender_role", sa.String(length=12), nullable=False, server_default="user"),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("client_message_id", sa.String(length=72), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("conversation_id", "client_message_id", name="ux_finder_messages_conversation_client_message"),
        )
        op.create_index("ix_finder_messages_conversation_id", "finder_messages", ["conversation_id"])
        op.create_index("ix_finder_messages_client_message_id", "finder_messages", ["client_message_id"])
        op.create_index("ix_finder_messages_created_at", "finder_messages", ["created_at"])

    if not _has_table("finder_search_states"):
        op.create_table(
            "finder_search_states",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("finder_conversations.id"), nullable=False, unique=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("spec_json", sa.Text(), nullable=True),
            sa.Column("last_result_ids_json", sa.Text(), nullable=True),
            sa.Column("next_offset", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_finder_search_states_conversation_id", "finder_search_states", ["conversation_id"])
        op.create_index("ix_finder_search_states_updated_at", "finder_search_states", ["updated_at"])

    if not _has_table("finder_listing_indexes"):
        op.create_table(
            "finder_listing_indexes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, unique=True),
            sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("searchable_text", sa.Text(), nullable=False),
            sa.Column("attributes_json", sa.Text(), nullable=True),
            sa.Column("indexed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_finder_listing_indexes_item_id", "finder_listing_indexes", ["item_id"])
        op.create_index("ix_finder_listing_indexes_source_fingerprint", "finder_listing_indexes", ["source_fingerprint"])
        op.create_index("ix_finder_listing_indexes_indexed_at", "finder_listing_indexes", ["indexed_at"])


def downgrade() -> None:
    # Finder is isolated from support/direct messages.  Dropping only these
    # additive tables is safe for a deliberate rollback, after operational
    # review; this task never runs the downgrade in production.
    for table, indexes in (
        ("finder_listing_indexes", ("ix_finder_listing_indexes_indexed_at", "ix_finder_listing_indexes_source_fingerprint", "ix_finder_listing_indexes_item_id")),
        ("finder_search_states", ("ix_finder_search_states_updated_at", "ix_finder_search_states_conversation_id")),
        ("finder_messages", ("ix_finder_messages_created_at", "ix_finder_messages_client_message_id", "ix_finder_messages_conversation_id")),
        ("finder_conversations", ("ix_finder_conversations_updated_at", "ix_finder_conversations_created_at", "ix_finder_conversations_status", "ix_finder_conversations_user_id")),
    ):
        if _has_table(table):
            for index in indexes:
                op.drop_index(index, table_name=table)
            op.drop_table(table)
