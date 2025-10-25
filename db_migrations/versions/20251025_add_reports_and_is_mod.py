"""add reports tables + users.is_mod"""

from alembic import op
import sqlalchemy as sa

# ========= IDs =========
revision = "add_reports_and_is_mod_20251025"
down_revision = "add_lat_lng_to_items_20251023"  # ← عدّلها لو كان آخر revision لديك مختلف
branch_labels = None
depends_on = None


def _bool_default():
    """إرجاع قيمة افتراضية متوافقة مع SQLite/PostgreSQL"""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("false")
    return sa.text("0")


def upgrade():
    # ===== users.is_mod =====
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("is_mod", sa.Boolean(), nullable=False, server_default=_bool_default())
        )
    # إزالة الـ server_default بعد الإنشاء (اختياري)
    op.alter_column("users", "is_mod", server_default=None)

    # ===== reports =====
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=True),
        sa.Column("image_index", sa.Integer(), nullable=True),  # رقم الصورة داخل المنشور (إن وجد)
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
    )

    op.create_index("ix_reports_item_id", "reports", ["item_id"])
    op.create_index("ix_reports_reporter_id", "reports", ["reporter_id"])
    op.create_index("ix_reports_status", "reports", ["status"])

    # ===== report_action_logs =====
    op.create_table(
        "report_action_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),  # delete / reject / warn / other
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_index("ix_report_action_logs_report_id", "report_action_logs", ["report_id"])
    op.create_index("ix_report_action_logs_actor_id", "report_action_logs", ["actor_id"])


def downgrade():
    # ===== report_action_logs =====
    op.drop_index("ix_report_action_logs_actor_id", table_name="report_action_logs")
    op.drop_index("ix_report_action_logs_report_id", table_name="report_action_logs")
    op.drop_table("report_action_logs")

    # ===== reports =====
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_index("ix_reports_reporter_id", table_name="reports")
    op.drop_index("ix_reports_item_id", table_name="reports")
    op.drop_table("reports")

    # ===== users.is_mod =====
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_mod")
