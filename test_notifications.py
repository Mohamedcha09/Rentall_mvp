# test_notifications.py  ← استبدل الملف كله بهذه النسخة
import os
from datetime import datetime, timezone

# حمّل .env من مجلد المشروع
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# الآن استورد دالة الإرسال من مشروعك
from app.emailer import send_email

EMAIL = os.getenv("TEST_EMAIL_TO") or os.getenv("EMAIL_USER")
HOST  = os.getenv("EMAIL_HOST")
PORT  = os.getenv("EMAIL_PORT")
USER  = os.getenv("EMAIL_USER")

print("ENV:", HOST, PORT, USER, EMAIL)

tests = [
    ("🔑 تفعيل الحساب", "<p>مرحبًا، هذا اختبار لبريد <b>تفعيل الحساب</b>.</p>"),
    ("🧾 إيصال الدفع", "<p>تم استلام الدفع بنجاح — هذا اختبار إيصال.</p>"),
    ("⚖️ القرار النهائي", "<p>تم إعلان القرار النهائي في قضية الوديعة.</p>"),
    ("🧨 انتهاء المهلة", "<p>انتهت مهلة الـ 24 ساعة دون رد المستأجر.</p>"),
    ("⏰ بدء مهلة 24h", "<p>بدأت الآن نافذة الـ 24 ساعة للرد على القرار.</p>"),
    ("🧍‍♂️ تم تعيينك لمراجعة قضية", "<p>تم تعيينك لمراجعة هذه القضية.</p>"),
    ("🔗 نجاح ربط Stripe", "<p>تم ربط حساب Stripe Connect بنجاح.</p>"),
    ("🪪 فشل ربط Stripe", "<p>فشل ربط Stripe Connect — تحقق من الإعدادات.</p>"),
]

now = datetime.now(timezone.utc).isoformat()
ok_all = True
for subj, html in tests:
    ok = send_email(
        to=EMAIL,
        subject=f"[RentAll Test {now}] {subj}",
        html_body=html,
        text_body=html,
    )
    print(f"{subj}: {'✅ تم الإرسال' if ok else '❌ فشل'}")
    ok_all = ok_all and ok

print("ALL:", "✅" if ok_all else "❌")
