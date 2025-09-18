# patch_users_is_verified.py
import os, sqlite3

DB = os.path.join(os.getcwd(), "app.db")
print("DB:", DB, "| exists:", os.path.exists(DB))
conn = sqlite3.connect(DB)
c = conn.cursor()

def has_col(table, col):
    c.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in c.fetchall())

if not has_col("users", "is_verified"):
    c.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 0")
    print("✔ Added users.is_verified (default 0)")
else:
    print("✓ users.is_verified already exists")

conn.commit()
conn.close()
print("✅ Done.")
