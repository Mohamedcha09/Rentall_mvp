# migrate_add_is_read.py
import os, sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")
print("DB:", DB_PATH)

if not os.path.exists(DB_PATH):
    raise SystemExit("❌ لم أجد app.db في هذا المسار. تأكد أنك تشغل السكربت من مجلد المشروع الصحيح.")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

def cols(table):
    c.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in c.fetchall()]

# == messages ==
try:
    mcols = cols("messages")
    print("messages cols before:", mcols)

    if "is_read" not in mcols:
        c.execute("ALTER TABLE messages ADD COLUMN is_read INTEGER DEFAULT 0")
        print("✔ Added messages.is_read")

    if "read_at" not in mcols:
        c.execute("ALTER TABLE messages ADD COLUMN read_at TEXT")
        print("✔ Added messages.read_at")

    conn.commit()
except sqlite3.OperationalError as e:
    print("⚠ Error altering messages:", e)

# == message_threads.item_id (لو لسه ناقص) ==
try:
    tcols = cols("message_threads")
    print("message_threads cols before:", tcols)
    if "item_id" not in tcols:
        c.execute("ALTER TABLE message_threads ADD COLUMN item_id INTEGER")
        print("✔ Added message_threads.item_id")
        conn.commit()
except sqlite3.OperationalError as e:
    print("⚠ Error altering message_threads:", e)

# طباعة بعد التعديل
try:
    print("messages cols after:", cols("messages"))
    print("message_threads cols after:", cols("message_threads"))
except Exception as e:
    print("ℹ Note:", e)

conn.close()
print("✅ Migration done.")
