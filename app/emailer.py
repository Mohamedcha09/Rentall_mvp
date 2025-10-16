# app/emailer.py
from __future__ import annotations
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# نستخدم requests فقط عند وجود مفتاح SendGrid
try:
    import requests  # type: ignore
except Exception:
    requests = None  # في لوكال عادة موجودة؛ على السيرفر تأكد من إضافتها للـ requirements.txt

DEFAULT_FROM = os.getenv("EMAIL_FROM") or os.getenv("EMAIL_USER") or "no-reply@example.com"

def _env_bool(v: str | None, default: bool = True) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")

def _send_via_sendgrid(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to: str | None = None,
) -> bool:
    """
    إرسال عبر SendGrid HTTP API.
    يحتاج:
      - SENDGRID_API_KEY
      - EMAIL_FROM (أو EMAIL_USER) كمرسل
    """
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key or requests is None:
        return False

    from_email = DEFAULT_FROM
    personalizations = [{"to": [{"email": to}]}]
    if cc:
        personalizations[0]["cc"] = [{"email": x} for x in cc if x]
    if bcc:
        personalizations[0]["bcc"] = [{"email": x} for x in bcc if x]

    payload = {
        "from": {"email": from_email},
        "subject": subject,
        "personalizations": personalizations,
        "content": [
            {"type": "text/plain", "value": (text_body or "")},
            {"type": "text/html", "value": (html_body or "")},
        ],
    }
    if reply_to:
        payload["reply_to"] = {"email": reply_to}

    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        # SendGrid يرجع 202 عند النجاح
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def _send_via_smtp(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to: str | None = None,
) -> bool:
    """
    إرسال عبر SMTP (Gmail).
    يعمل محليًا من جهازك، لكنه غالبًا محجوب على السيرفر.
    يحتاج:
      EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS, EMAIL_USE_TLS
    """
    host = os.getenv("EMAIL_HOST", "")
    port = int(os.getenv("EMAIL_PORT", "587") or 0)
    user = os.getenv("EMAIL_USER", "")
    pwd  = os.getenv("EMAIL_PASS", "")
    use_tls = _env_bool(os.getenv("EMAIL_USE_TLS"), True)

    if not (host and port and user and pwd and to):
        return False

    # بناء الرسالة
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = DEFAULT_FROM or user
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to

    msg.attach(MIMEText((text_body or ""), "plain", "utf-8"))
    msg.attach(MIMEText((html_body or ""), "html", "utf-8"))

    recipients = [to] + (cc or []) + (bcc or [])
    try:
        smtp = smtplib.SMTP(host, port, timeout=20)
        smtp.ehlo()
        if use_tls and port == 587:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(user, pwd)
        smtp.sendmail(msg["From"], recipients, msg.as_string())
        try:
            smtp.quit()
        except Exception:
            pass
        return True
    except Exception:
        return False


def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to: str | None = None,
) -> bool:
    """
    واجهة موحّدة:
      1) تجرّب SendGrid إذا كان SENDGRID_API_KEY موجودًا (موصى به على السيرفر).
      2) وإلا تستخدم SMTP.
    """
    # 1) SendGrid أولاً (مخصص للسيرفر)
    if os.getenv("SENDGRID_API_KEY"):
        ok = _send_via_sendgrid(to, subject, html_body, text_body, cc, bcc, reply_to)
        if ok:
            return True

    # 2) SMTP كخيار احتياطي (يعمل محليًا)
    return _send_via_smtp(to, subject, html_body, text_body, cc, bcc, reply_to)
