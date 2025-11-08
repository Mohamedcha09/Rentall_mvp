import sqlite3

db_path = "app.db"   # Change it if the database is elsewhere

conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("PRAGMA table_info(message_threads)")
cols = [r[1] for r in c.fetchall()]
print("Existing columns before:", cols)

if "item_id" not in cols:
    c.execute("ALTER TABLE message_threads ADD COLUMN item_id INTEGER")
    conn.commit()
    print("✅ Column item_id added successfully")
else:
    print("ℹ️ Column item_id already exists")

c.execute("PRAGMA table_info(message_threads)")
print("Existing columns after:", [r[1] for r in c.fetchall()])

conn.close()



