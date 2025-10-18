# app/email_service.py
from __future__ import annotations
import os
import requests
from typing import Optional, Iterable, Union, List

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# =========================
# إعدادات SendGrid من .env
# =========================
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL       = os.getenv("FROM_EMAIL", "")
FROM_NAME        = os.getenv("FROM_NAME", "Rentall Notifications")

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"

def _normalize_list(value: Optional[Union[str, Iterable[str]]]) -> List[str]:
    """يحوّل قيمة واحدة أو قائمة إلى قائمة نظيفة بدون فراغات"""
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    return [v.strip() for v in value if v and v.strip()]

def send_email(
    to: Union[str, Iterable[str]],
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    cc: Optional[Union[str, Iterable[str]]] = None,
    bcc: Optional[Union[str, Iterable[str]]] = None,
    reply_to: Optional[str] = None,
) -> bool:
    """
    إرسال بريد إلكتروني عبر SendGrid API.
    يُرجع True عند النجاح أو False عند الفشل.
    """
    if not SENDGRID_API_KEY:
        print("[email_service] ❌ SENDGRID_API_KEY مفقود من .env")
        return False
    if not FROM_EMAIL:
        print("[email_service] ❌ FROM_EMAIL مفقود من .env")
        return False

    recipients = _normalize_list(to)
    if not recipients:
        print("[email_service] ⚠️ لا يوجد مستلم محدد")
        return False

    payload = {
        "personalizations": [
            {
                "to": [{"email": addr} for addr in recipients],
                "subject": subject or "(No subject)",
            }
        ],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "content": [
            {"type": "text/plain", "value": text_body or ""},
            {"type": "text/html", "value": html_body or ""},
        ],
    }

    # دعم cc / bcc
    cc_list = _normalize_list(cc)
    bcc_list = _normalize_list(bcc)
    if cc_list:
        payload["personalizations"][0]["cc"] = [{"email": a} for a in cc_list]
    if bcc_list:
        payload["personalizations"][0]["bcc"] = [{"email": a} for a in bcc_list]

    # Reply-To
    if reply_to:
        payload["reply_to"] = {"email": reply_to.strip()}

    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(SENDGRID_API_URL, json=payload, headers=headers, timeout=15)
        if r.status_code in (200, 202):
            print(f"[email_service] ✅ Email sent to {recipients}")
            return True
        else:
            print(f"[email_service] ❌ SendGrid error {r.status_code}: {r.text[:400]}")
            return False
    except Exception as e:
        print(f"[email_service] ⚠️ Exception while sending email: {e}")
        return False


# اختبار سريع من الطرف المحلي (اختياري)
if __name__ == "__main__":
    test_to = os.getenv("TEST_EMAIL_TO", FROM_EMAIL)
    ok = send_email(
        to=test_to,
        subject="📨 SendGrid Test — Rentall",
        html_body="<h2>It works 🎉</h2><p>This is a test email via SendGrid.</p>",
        text_body="It works! This is a test email via SendGrid."
    )
    print("Test send:", "OK ✅" if ok else "FAILED ❌")


