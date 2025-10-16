# app/email_service.py
import os
import requests

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_SENDER = os.getenv("SENDGRID_SENDER", "sevorapp026@gmail.com")

def send_email(to: str, subject: str, html_body: str, text_body: str = None):
    """
    يرسل البريد الإلكتروني باستخدام SendGrid API.
    """
    if not SENDGRID_API_KEY:
        print("❌ SENDGRID_API_KEY غير موجود")
        return False

    if not to or not subject:
        print("❌ المتغيرات المطلوبة غير كاملة")
        return False

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": SENDGRID_SENDER, "name": "RentAll"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_body or subject},
            {"type": "text/html", "value": html_body or subject}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code in [200, 202]:
            print(f"✅ Email sent to {to}")
            return True
        else:
            print(f"❌ SendGrid Error: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception during send_email: {e}")
        return False
