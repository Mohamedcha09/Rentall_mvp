# migrate_20250915.py
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")
print("DB:", DB_PATH)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

def table_cols(table):
    c.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in c.fetchall()]

# تأكد أن قاعدة البيانات تحتوي الجداول، وإن لم تكن موجودة اصنعها
try:
    cols_users = table_cols("users")
except sqlite3.OperationalError:
    # لو الجداول غير موجودة، أنشئها عبر SQLAlchemy
    print("Tables not found. Creating all tables via SQLAlchemy ...")
    from app.database import Base, engine
    Base.metadata.create_all(bind=engine)

# 1) messages.is_read
try:
    cols = table_cols("messages")
    print("messages columns:", cols)
    if "is_read" not in cols:
        c.execute("ALTER TABLE messages ADD COLUMN is_read BOOLEAN DEFAULT 0")
        print("-> added messages.is_read")
    else:
        print("-> messages.is_read already exists")
except sqlite3.OperationalError as e:
    print("Error on messages:", e)

# 2) message_threads.item_id
try:
    cols = table_cols("message_threads")
    print("message_threads columns:", cols)
    if "item_id" not in cols:
        c.execute("ALTER TABLE message_threads ADD COLUMN item_id INTEGER")
        print("-> added message_threads.item_id")
    else:
        print("-> message_threads.item_id already exists")
except sqlite3.OperationalError as e:
    print("Error on message_threads:", e)

conn.commit()
conn.close()
print("Migration done.")
