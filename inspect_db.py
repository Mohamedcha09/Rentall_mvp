# inspect_db.py
from app.database import engine

# ==== جداول نريد فحصها + الأعمدة المطلوبة لكل جدول ====
REQUIRED = {
    "users": [
        "id","first_name","last_name","email","phone","password_hash",
        # Stripe / payouts + أدوار
        "stripe_account_id","payouts_enabled","role","status",
        # التحقق و الأفاتار و التواريخ
        "is_verified","verified_at","verified_by_id","created_at","updated_at","avatar_path",
        # صلاحية متحكم الوديعة
        "is_deposit_manager",
        # الشارات
        "badge_admin","badge_new_yellow","badge_pro_green","badge_pro_gold",
        "badge_purple_trust","badge_renter_green","badge_orange_stars",
    ],
    "bookings": [
        "id","item_id","renter_id","owner_id",
        "start_date","end_date","days",
        "price_per_day_snapshot","total_amount",
        "status","created_at","updated_at",

        # طريقة الدفع و مبالغ
        "payment_method","platform_fee","rent_amount","hold_deposit_amount",

        # أونلاين/سترايب
        "online_status","online_checkout_id","online_payment_intent_id",
        "owner_payout_amount","rent_released_at",

        # الوديعة
        "deposit_status","deposit_hold_intent_id","deposit_refund_id","deposit_capture_id",
        "deposit_amount","deposit_hold_id","deposit_charged_amount",

        # قرارات وتايملاين إضافي
        "owner_decision","payment_status",
        "returned_at","owner_return_note",
        # إن وُجدت في مشروعك:
        "accepted_at","rejected_at","picked_up_at","timeline_created_at",
        "timeline_owner_decided_at","timeline_payment_method_chosen_at",
        "timeline_paid_at","timeline_renter_received_at",
    ],
    "messages": [
        "id","thread_id","sender_id","body","created_at",
        "is_read","read_at",
    ],
}

def pragma_table_info(table: str):
    with engine.begin() as conn:
        try:
            rows = conn.exec_driver_sql(f"PRAGMA table_info('{table}')").fetchall()
        except Exception as e:
            print(f"⚠️  فشل قراءة {table}: {e}")
            return []
    return rows

def list_tables():
    with engine.begin() as conn:
        # يعمل مع SQLite: قائمة الجداول من sqlite_master
        rows = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]

def check_table(table: str, required_cols: list[str]):
    rows = pragma_table_info(table)
    present = [r[1] for r in rows]  # r[1] = column name
    present_set = set(present)
    required_set = set(required_cols)

    missing = [c for c in required_cols if c not in present_set]
    extra   = [c for c in present if c not in required_set]

    print(f"\n===== جدول: {table} =====")
    print("الأعمدة الموجودة حالياً:")
    for c in present:
        print("  -", c)

    print("\nمطابقة الأعمدة المطلوبة:")
    for c in required_cols:
        mark = "✅" if c in present_set else "❌"
        print(f"  {mark} {c}")

    if missing:
        print("\n❌ أعمدة ناقصة (بحسب الخطة):")
        for c in missing:
            print("  -", c)
    else:
        print("\n✅ لا توجد أعمدة ناقصة في هذا الجدول بحسب القائمة المحددة.")

    if extra:
        print("\nℹ️ أعمدة إضافية موجودة وليست في القائمة المرجعية (ليست مشكلة):")
        for c in extra:
            print("  -", c)

def main():
    print("🔎 فحص هيكل قاعدة البيانات (SQLite)")
    all_tables = list_tables()
    print("\nالجداول الموجودة في قاعدة البيانات:")
    for t in all_tables:
        print("  •", t)

    # افحص الجداول المحددة أعلاه فقط
    for table, cols in REQUIRED.items():
        if table not in all_tables:
            print(f"\n❌ الجدول {table} غير موجود في قاعدة البيانات")
            continue
        check_table(table, cols)

if __name__ == "__main__":
    main()