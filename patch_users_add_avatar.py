# patch_users_add_avatar.py
import sqlite3

db_path = "app.db"  # غيّره لو اسم قاعدة بياناتك مختلف
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# أضف العمود لو مش موجود
cur.execute("""
PRAGMA table_info(users);
""")
cols = [r[1] for r in cur.fetchall()]
if "avatar_path" not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN avatar_path TEXT;")
    print("✅ Added column users.avatar_path")
else:
    print("ℹ️ Column users.avatar_path already exists")

conn.commit()
conn.close()
