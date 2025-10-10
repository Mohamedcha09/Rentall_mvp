# -*- coding: utf-8 -*-
"""
إضافة الأعمدة والجدول الناقصة لخطّة الوديعة (SQLite فقط)
- لا يحذف أي بيانات
- يضيف فقط الأعمدة الناقصة
- ينشئ جدول deposit_evidences إذا لم يكن موجودًا

التشغيل:
    (venv) $ python migrate_add_deposit_cols.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("app.db")  # تأكد أن هذا هو اسم قاعدة بياناتك


def has_table(conn, name: str) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,))
    return cur.fetchone() is not None


def table_columns(conn, table: str) -> set:
    cols = set()
    try:
        for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall():
            cols.add(row[1])
    except sqlite3.OperationalError:
        pass
    return cols


def add_column_if_missing(conn, table: str, col: str, ddl: str):
    cols = table_columns(conn, table)
    if col not in cols:
        print(f"  + adding {table}.{col} ...")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl};")


def create_deposit_evidences_if_missing(conn):
    if not has_table(conn, "deposit_evidences"):
        print("  + creating table deposit_evidences ...")
        conn.execute("""
        CREATE TABLE deposit_evidences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            by_user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,               -- 'image' | 'video' | 'doc'
            file_path TEXT NOT NULL,
            caption TEXT,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (booking_id) REFERENCES bookings(id),
            FOREIGN KEY (by_user_id) REFERENCES users(id)
        );
        """)
    else:
        print("  ✓ deposit_evidences table already exists.")


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"❌ لم أجد قاعدة البيانات: {DB_PATH.resolve()}")

    print("🔧 بدء ترقية الأعمدة (SQLite)")
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        # ===== users =====
        users_cols = table_columns(conn, "users")
        if users_cols:
            print("• users")
            add_column_if_missing(conn, "users", "badge_admin", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "users", "badge_new_yellow", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "users", "badge_pro_green", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "users", "badge_pro_gold", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "users", "badge_purple_trust", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "users", "badge_renter_green", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "users", "badge_orange_stars", "INTEGER NOT NULL DEFAULT 0")

        # ===== bookings =====
        bookings_cols = table_columns(conn, "bookings")
        if bookings_cols:
            print("• bookings")

            # ---- الدفع أونلاين ----
            add_column_if_missing(conn, "bookings", "payment_method", "TEXT")
            add_column_if_missing(conn, "bookings", "platform_fee", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "bookings", "rent_amount", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "bookings", "hold_deposit_amount", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "bookings", "online_status", "TEXT")
            add_column_if_missing(conn, "bookings", "online_checkout_id", "TEXT")
            add_column_if_missing(conn, "bookings", "online_payment_intent_id", "TEXT")
            add_column_if_missing(conn, "bookings", "owner_payout_amount", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "bookings", "rent_released_at", "DATETIME")

            # ---- الوديعة ----
            add_column_if_missing(conn, "bookings", "deposit_status", "TEXT")
            add_column_if_missing(conn, "bookings", "deposit_hold_intent_id", "TEXT")
            add_column_if_missing(conn, "bookings", "deposit_refund_id", "TEXT")
            add_column_if_missing(conn, "bookings", "deposit_capture_id", "TEXT")
            add_column_if_missing(conn, "bookings", "deposit_amount", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "bookings", "deposit_hold_id", "TEXT")
            add_column_if_missing(conn, "bookings", "owner_decision", "TEXT")
            add_column_if_missing(conn, "bookings", "payment_status", "TEXT")

            # ---- الإرجاع ----
            add_column_if_missing(conn, "bookings", "returned_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "owner_return_note", "TEXT")

            # ---- الـ Timeline ----
            add_column_if_missing(conn, "bookings", "accepted_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "rejected_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "picked_up_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "timeline_created_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "timeline_owner_decided_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "timeline_payment_method_chosen_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "timeline_paid_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "timeline_renter_received_at", "DATETIME")

            # ---- مهَل و Claim ----
            add_column_if_missing(conn, "bookings", "deadline_owner_report_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "deadline_renter_reply_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "deadline_dm_decision_at", "DATETIME")
            add_column_if_missing(conn, "bookings", "auto_release_scheduled", "INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(conn, "bookings", "assigned_dm_id", "INTEGER")

        # ===== جدول الأدلة =====
        print("• deposit_evidences")
        create_deposit_evidences_if_missing(conn)

        conn.commit()

    print("✅ تمّت إضافة الأعمدة/الجدول الناقصة بنجاح.")


if __name__ == "__main__":
    main()