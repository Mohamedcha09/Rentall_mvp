# app/email_service.py  — SendGrid API sender
import os, json, urllib.request

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL       = os.getenv("FROM_EMAIL", "")  # يجب أن يكون مُوثقًا في SendGrid

def send_email(to: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """
    يرسل بريدًا عبر SendGrid API. يرجع True عند النجاح.
    """
    if not (SENDGRID_API_KEY and FROM_EMAIL and to and subject and html_body):
        print("❌ send_email: missing env or params")
        return False

    if not text_body:
        text_body = " "

    data = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": FROM_EMAIL},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_body},
            {"type": "text/html",  "value": html_body},
        ],
        # ✅ مهم: تعطيل استبدال الروابط (click tracking) حتى لا يفسد زر التفعيل في تطبيقات الهاتف
        "tracking_settings": {
            "click_tracking": {"enable": False, "enable_text": False}
        },
    }

    req = urllib.request.Request(
        url="https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            ok = (200 <= resp.status < 300)  # SendGrid يعيد 202
            if not ok:
                print("❌ send_email resp:", resp.status, resp.read())
            return ok
    except Exception as e:
        print("❌ send_email exception:", e)
        return False