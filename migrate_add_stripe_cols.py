import sqlite3

# الاتصال بقاعدة البيانات
db_path = "app.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# --- إضافة الأعمدة الجديدة إن لم تكن موجودة ---
try:
    cursor.execute("ALTER TABLE users ADD COLUMN stripe_account_id TEXT")
    print("✅ تمت إضافة العمود stripe_account_id")
except sqlite3.OperationalError:
    print("ℹ️ العمود stripe_account_id موجود مسبقًا")

try:
    cursor.execute("ALTER TABLE users ADD COLUMN payouts_enabled BOOLEAN DEFAULT 0")
    print("✅ تمت إضافة العمود payouts_enabled")
except sqlite3.OperationalError:
    print("ℹ️ العمود payouts_enabled موجود مسبقًا")

conn.commit()

# --- التحقق ---
print("\n📋 الأعمدة في جدول users:")
cursor.execute("PRAGMA table_info(users)")
for r in cursor.fetchall():
    print(r)

conn.close()
print("\n✅ تمّت العملية بنجاح.")