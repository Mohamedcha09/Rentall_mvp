# app/email_service.py — SendGrid API sender
import os, json, urllib.request, re

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL       = os.getenv("FROM_EMAIL", "")
FROM_NAME        = os.getenv("FROM_NAME", "SEVOR • RentAll")

def send_email(to: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """
    يرسل بريدًا عبر SendGrid API.
    ✅ متوافق مع Gmail / Outlook على الهاتف.
    ✅ يرسل HTML + نص بديل (text/plain) لضمان عمل الرابط.
    """
    if not (SENDGRID_API_KEY and FROM_EMAIL and to and subject and html_body):
        print("❌ send_email: missing environment vars or parameters.")
        return False

    if not text_body:
        # توليد نص بديل بسيط يحتوي على أول رابط
        text_body = "لتفعيل حسابك افتح الرابط التالي:\n" + _extract_first_link(html_body)

    # محتوى البريد
    data = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_body},
            {"type": "text/html",  "value": html_body}
        ],
        # إعدادات الأمان والتتبع
        "tracking_settings": {
            "click_tracking": {"enable": False, "enable_text": False},  # تعطيل تتبع الروابط (مهم للموبايل)
            "open_tracking": {"enable": False}
        },
        "mail_settings": {
            "sandbox_mode": {"enable": False}
        }
    }

    req = urllib.request.Request(
        url="https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if 200 <= resp.status < 300:
                print("✅ Email sent successfully:", to)
                return True
            else:
                print("❌ SendGrid error:", resp.status)
                return False
    except Exception as e:
        print("❌ send_email exception:", e)
        return False


def _extract_first_link(html: str) -> str:
    """استخراج أول رابط من HTML لاستخدامه في النص البديل."""
    match = re.search(r'href=["\']([^"\']+)["\']', html or "", re.I)
    return match.group(1) if match else ""