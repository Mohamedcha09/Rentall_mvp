# patch_messages_columns.py
import os, sqlite3

DB = os.path.join(os.getcwd(), "app.db")
print("DB:", DB, "| exists:", os.path.exists(DB))
if not os.path.exists(DB):
    print("❌ لا يوجد ملف قاعدة بيانات app.db في هذا المجلد.")
    raise SystemExit(1)

conn = sqlite3.connect(DB)
c = conn.cursor()

def cols(table):
    c.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in c.fetchall()]

# اطبع الأعمدة قبل التعديل
try:
    before = cols("messages")
    print("messages BEFORE:", before)
except Exception as e:
    print("❌ لا يوجد جدول messages:", e)
    conn.close()
    raise SystemExit(1)

# أضف is_read إذا كان مفقود
if "is_read" not in before:
    try:
        c.execute("ALTER TABLE messages ADD COLUMN is_read INTEGER DEFAULT 0")
        print("✔ Added messages.is_read")
    except Exception as e:
        print("⚠ error adding is_read:", e)
else:
    print("✓ messages.is_read موجود أصلاً")

# أضف read_at إذا كان مفقود
# نستعمل TEXT (ISO string) — مناسب لـ SQLite
after_tmp = cols("messages")
if "read_at" not in after_tmp:
    try:
        c.execute("ALTER TABLE messages ADD COLUMN read_at TEXT")
        print("✔ Added messages.read_at")
    except Exception as e:
        print("⚠ error adding read_at:", e)
else:
    print("✓ messages.read_at موجود أصلاً")

conn.commit()

# اطبع الأعمدة بعد التعديل
print("messages AFTER:", cols("messages"))

conn.close()
print("✅ Done.")
