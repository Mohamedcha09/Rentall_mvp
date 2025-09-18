import sqlite3
from app.database import engine

# الحصول على مسار قاعدة البيانات من SQLAlchemy
db_path = engine.url.database or "app.db"
print("DB path:", db_path)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# هل الجدول موجود؟
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message_threads'")
exists = c.fetchone() is not None
if not exists:
    print("❌ جدول message_threads غير موجود. شغّل create_all أولاً.")
    conn.close()
    raise SystemExit(1)

# أعمدة الجدول
c.execute("PRAGMA table_info(message_threads)")
cols = [r[1] for r in c.fetchall()]
print("الأعمدة قبل:", cols)

# إضافة العمود لو ناقص
if "item_id" not in cols:
    c.execute("ALTER TABLE message_threads ADD COLUMN item_id INTEGER")
    conn.commit()
    print("✅ تمت إضافة العمود item_id")
else:
    print("ℹ️ العمود item_id موجود مسبقاً")

# اعرض بعد التعديل
c.execute("PRAGMA table_info(message_threads)")
print("الأعمدة بعد:", [r[1] for r in c.fetchall()])

conn.close()
