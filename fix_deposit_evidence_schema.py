# fix_deposit_evidence_schema.py
# سكربت بسيط يفحص أعمدة جدول deposit_evidences ويضيف الناقص منها (SQLite)
import os, sqlite3

DB_CANDIDATES = ["app.db", "app.sqlite"]
db_path = None
for p in DB_CANDIDATES:
    if os.path.exists(p):
        db_path = p
        break

if not db_path:
    # حاول في مسار app/ إذا كانت القاعدة هناك
    for p in [os.path.join("app", "app.db"), os.path.join("app", "app.sqlite")]:
        if os.path.exists(p):
            db_path = p
            break

if not db_path:
    raise SystemExit("❌ لم أجد قاعدة البيانات (app.db أو app.sqlite). ضع السكربت بجانب القاعدة أو حدّث المسار داخل الملف.")

print(f"🔧 استخدام قاعدة البيانات: {db_path}")

con = sqlite3.connect(db_path)
cur = con.cursor()

def table_columns(table):
    cur.execute(f"PRAGMA table_info('{table}')")
    return {row[1] for row in cur.fetchall()}

# تأكد أن الجدول موجود
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='deposit_evidences'")
row = cur.fetchone()
if not row:
    con.close()
    raise SystemExit("❌ الجدول deposit_evidences غير موجود. تأكد من تشغيل app أولاً لإنشاء الجداول أو من ملف models.")

# الأعمدة التي يجب أن تكون موجودة
needed = {
    "id": "INTEGER",
    "booking_id": "INTEGER",
    "uploader_id": "INTEGER",
    "side": "TEXT",
    "kind": "TEXT",
    "file_path": "TEXT",
    "description": "TEXT",
    "created_at": "DATETIME"
}

existing = table_columns("deposit_evidences")
print("📋 الأعمدة الحالية:", ", ".join(sorted(existing)))

missing = [c for c in needed.keys() if c not in existing]

if not missing:
    print("✅ لا توجد أعمدة ناقصة في deposit_evidences.")
else:
    print("⚠️ أعمدة ناقصة سيتم إضافتها:", ", ".join(missing))
    for col in missing:
        sql_type = needed[col]
        # SQLite يسمح بإضافة العمود بدون DEFAULT (سيكون NULL للسجلات القديمة)
        alter = f"ALTER TABLE deposit_evidences ADD COLUMN {col} {sql_type}"
        print(f"➡️  {alter}")
        cur.execute(alter)
    con.commit()
    print("✅ تم إضافة الأعمدة الناقصة بنجاح.")

# طباعة الأعمدة بعد التعديل
final_cols = table_columns("deposit_evidences")
print("📌 الأعمدة الآن:", ", ".join(sorted(final_cols)))

con.close()
print("🎉 اكتمل السكربت بدون أخطاء.")