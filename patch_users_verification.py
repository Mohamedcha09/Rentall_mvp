# patch_users_verification.py
import sqlite3, os, datetime

DB = os.path.abspath("app.db")
con = sqlite3.connect(DB)
c = con.cursor()

def cols(t): 
    c.execute(f"PRAGMA table_info({t})")
    return [r[1] for r in c.fetchall()]

existing = cols("users")

if "is_verified" not in existing:
    c.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")

if "verified_at" not in existing:
    c.execute("ALTER TABLE users ADD COLUMN verified_at TEXT")

if "verified_by_id" not in existing:
    c.execute("ALTER TABLE users ADD COLUMN verified_by_id INTEGER")

con.commit()
con.close()
print("✅ users table updated with verification columns")
