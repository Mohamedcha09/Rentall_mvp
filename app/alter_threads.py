import sqlite3

db_path = "app.db"   # غيّره إذا قاعدة البيانات في مكان آخر

conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("PRAGMA table_info(message_threads)")
cols = [r[1] for r in c.fetchall()]
print("الأعمدة الموجودة قبل:", cols)

if "item_id" not in cols:
    c.execute("ALTER TABLE message_threads ADD COLUMN item_id INTEGER")
    conn.commit()
    print("✅ تمت إضافة العمود item_id بنجاح")
else:
    print("ℹ️ العمود item_id موجود مسبقاً")

c.execute("PRAGMA table_info(message_threads)")
print("الأعمدة الموجودة بعد:", [r[1] for r in c.fetchall()])

conn.close()
