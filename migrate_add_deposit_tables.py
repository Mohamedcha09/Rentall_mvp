# migrate_add_deposit_tables.py
import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "app.db")

def has_col(cur, table, col):
    cur.execute(f"PRAGMA table_info('{table}')")
    return any(r[1] == col for r in cur.fetchall())

def ensure_user_flag(cur):
    # علم صلاحية مدير الوديعة
    if not has_col(cur, "users", "is_deposit_manager"):
        cur.execute("ALTER TABLE users ADD COLUMN is_deposit_manager INTEGER NOT NULL DEFAULT 0")

def create_cases_tables(cur):
    # جدول قضايا الوديعة
    cur.execute("""
    CREATE TABLE IF NOT EXISTS deposit_cases (
      id INTEGER PRIMARY KEY,
      booking_id INTEGER NOT NULL,
      owner_id INTEGER NOT NULL,
      renter_id INTEGER NOT NULL,
      deposit_amount INTEGER NOT NULL DEFAULT 0,
      issue_type TEXT NOT NULL,                -- delay | damage | loss_theft | other
      status TEXT NOT NULL DEFAULT 'pending',  -- pending | in_review | resolved
      assignee_id INTEGER,
      reported_at TEXT,
      resolved_at TEXT,
      evidence_json TEXT
    );
    """)
    # سجل الإجراءات على القضية
    cur.execute("""
    CREATE TABLE IF NOT EXISTS deposit_action_logs (
      id INTEGER PRIMARY KEY,
      case_id INTEGER NOT NULL,
      actor_id INTEGER,
      action TEXT NOT NULL,      -- claim | decision_refund | decision_partial | decision_full | note
      note TEXT,
      amount INTEGER DEFAULT 0,
      created_at TEXT NOT NULL
    );
    """)

def ensure_booking_cols(cur):
    # أعمدة مساعدة في الحجوزات إن كانت ناقصة (تتعلق بالوديعة فقط)
    if not has_col(cur, "bookings", "return_confirmed_by_owner_at"):
        cur.execute("ALTER TABLE bookings ADD COLUMN return_confirmed_by_owner_at TEXT")
    if not has_col(cur, "bookings", "deposit_charged_amount"):
        cur.execute("ALTER TABLE bookings ADD COLUMN deposit_charged_amount INTEGER NOT NULL DEFAULT 0")

def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        ensure_user_flag(cur)
        create_cases_tables(cur)
        ensure_booking_cols(cur)
        con.commit()
        print("✅ Deposit migration completed")
    finally:
        con.close()

if __name__ == "__main__":
    main()
