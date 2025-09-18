# patch_users_verify_columns.py
# يضيف أعمدة التوثيق لحقل users إن كانت مفقودة (SQLite)
import os
import sqlite3

BASE = os.getcwd()  # يفترض أنك تشغل السكربت من مجلد المشروع
DB_PATH = os.path.join(BASE, "app.db")

print("📦 قاعدة البيانات:", DB_PATH, "| موجود؟", os.path.exists(DB_PATH))
if not os.path.exists(DB_PATH):
    raise SystemExit("❌ لم يتم العثور على app.db — شغّل المشروع مرة واحدة لإنشائها أو تحقّق من المسار.")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

def cols(table):
    c.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in c.fetchall()]

def add_col_if_missing(table, col, ddl):
    current = cols(table)
    if col not in current:
        print(f"➕ إضافة العمود {table}.{col} ...")
        c.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        print(f"✔ تم إضافة {col}.")
    else:
        print(f"✓ {table}.{col} موجود أصلاً.")

# تأكّد أن جدول users موجود
try:
    existing = cols("users")
    if not existing:
        print("⚠ جدول users موجود لكنه بدون أعمدة؟ تحقق من قاعدة البيانات.")
except Exception as e:
    print("❌ لا يوجد جدول users:", e)
    conn.close()
    raise SystemExit(1)

print("users BEFORE:", cols("users"))

# ملاحظة: SQLite لا يملك نوع DateTime/Boolean حقيقي — نستخدم أنواع بسيطة
# Boolean => INTEGER DEFAULT 0
# DateTime => TEXT
add_col_if_missing("users", "is_verified",    "is_verified INTEGER NOT NULL DEFAULT 0")
add_col_if_missing("users", "verified_at",    "verified_at TEXT")
add_col_if_missing("users", "verified_by_id", "verified_by_id INTEGER")

conn.commit()
print("users AFTER:", cols("users"))
conn.close()
print("✅ تم.")
