# inspect_db.py
import os, sqlite3

DB = os.path.join(os.getcwd(), "app.db")
print("DB path:", DB, "| exists:", os.path.exists(DB))
conn = sqlite3.connect(DB)
c = conn.cursor()

print("\n== Tables ==")
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
for (name,) in c.fetchall():
    print("-", name)

def cols(table):
    c.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in c.fetchall()]

print("\nmessages columns:", end=" ")
try:
    print(cols("messages"))
except Exception as e:
    print("ERROR:", e)

conn.close()
