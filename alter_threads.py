import sqlite3

# إذا قاعدة بياناتك باسم/مكان مختلف غيّر هذا المسار
db_path = "app.db"

conn = sqlite3.connect(db_path)
c = conn.cursor()

# أعمدة الجدول قبل
c.execute("PRAGMA table_info(message_threads)")
cols = [r[1] for r in c.fetchall()]
print("الأعمدة قبل:", cols)

# أضف item_id إذا غير موجود
if "item_id" not in cols:
    c.execute("ALTER TABLE message_threads ADD COLUMN item_id INTEGER")
    conn.commit()
    print("✅ تمت إضافة العمود item_id")
else:
    print("ℹ️ العمود item_id موجود مسبقاً")

# أعمدة الجدول بعد
c.execute("PRAGMA table_info(message_threads)")
print("الأعمدة بعد:", [r[1] for r in c.fetchall()])

conn.close()
