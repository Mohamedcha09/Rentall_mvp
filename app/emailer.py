# app/emailer.py
import os, json, requests
from email.utils import formataddr

# ============================================
#  📧  خدمة إرسال البريد عبر SendGrid (بديل آمن يعمل على Render)
# ============================================

# رابط الموقع (لإضافة روابط التفعيل وغيرها)
SITE_URL = (os.getenv("SITE_URL") or "http://localhost:8000").rstrip("/")

# إعدادات SendGrid (مفاتيح من البيئة)
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
SENDGRID_SENDER = (os.getenv("SENDGRID_SENDER", "") or os.getenv("EMAIL_USER", "")).strip()


# ----------------------------
# 🧩 تكوين رؤوس الطلب (Headers)
# ----------------------------
def _sg_headers():
    return {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }


# ----------------------------
# 🧾 إنشاء Payload للإرسال
# ----------------------------
def _sg_payload(to, subject, html_body, text_body=None, cc=None, bcc=None, reply_to=None):
    def _addr(x):
        if not x:
            return None
        if isinstance(x, (list, tuple)):
            return [{"email": e} for e in x if e]
        return [{"email": x}]

    data = {
        "personalizations": [{
            "to": _addr(to),
            **({"cc": _addr(cc)} if cc else {}),
            **({"bcc": _addr(bcc)} if bcc else {}),
        }],
        "from": {"email": SENDGRID_SENDER, "name": "Rentall"},
        **({"reply_to": {"email": reply_to}} if reply_to else {}),
        "subject": subject or "(no subject)",
        "content": [
            {"type": "text/plain", "value": (text_body or "")},
            {"type": "text/html", "value": (html_body or text_body or "")},
        ],
    }
    return data


# ----------------------------
# 🚀 الدالة الرئيسية للإرسال
# ----------------------------
def send_email(to, subject, html_body, text_body=None, cc=None, bcc=None, reply_to=None) -> bool:
    """
    ترسل البريد الإلكتروني عبر SendGrid (Render لا يسمح بـ SMTP).
    ترجع True إذا نجح الإرسال.
    """
    if not (SENDGRID_API_KEY and SENDGRID_SENDER and to):
        print("[EMAILER] Missing SendGrid environment variables.")
        return False

    try:
        payload = _sg_payload(to, subject, html_body, text_body, cc, bcc, reply_to)
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers=_sg_headers(),
            data=json.dumps(payload),
            timeout=20
        )
        if resp.status_code == 202:
            print(f"[EMAIL SENT] to {to} ✅")
            return True
        else:
            print(f"[EMAIL FAILED] {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        print("[EMAIL ERROR]", e)
        return False


# ----------------------------
# 🧠 أداة اختبار وتشخيص
# ----------------------------
def _diag_send(to: str) -> dict:
    """
    دالة اختبار داخلية يمكن استدعاؤها من /admin/debug/email/send
    """
    if not (SENDGRID_API_KEY and SENDGRID_SENDER):
        return {"ok": False, "stage": "env", "note": "SENDGRID_API_KEY or SENDER missing"}

    payload = _sg_payload(
        to,
        "RentAll — Test Email (SendGrid)",
        "<p>✅ اختبار إرسال من RentAll عبر SendGrid.</p>",
        "اختبار إرسال من RentAll عبر SendGrid"
    )

    try:
        r = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers=_sg_headers(),
            data=json.dumps(payload),
            timeout=20
        )
        return {
            "ok": (r.status_code == 202),
            "status": r.status_code,
            "text": r.text[:300]
        }
    except Exception as e:
        return {"ok": False, "stage": "http", "error": str(e)}
