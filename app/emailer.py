# app/emailer.py
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Sequence

# ====== اختياري: تحميل قوالب Jinja إذا كانت موجودة ======
try:
    from fastapi.templating import Jinja2Templates  # للانسجام مع مشروعك
    from pathlib import Path
    _TPL_DIR = Path(__file__).parent / "templates" / "email"
    _templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
except Exception:
    _templates = None

# ====== SendGrid ======
_SENDGRID_KEY = os.getenv("SENDGRID_API_KEY") or ""
_SENDGRID_SENDER = os.getenv("SENDGRID_SENDER") or ""

def _send_via_sendgrid(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str],
    cc: Optional[Sequence[str]] = None,
    bcc: Optional[Sequence[str]] = None,
    reply_to: Optional[str] = None,
) -> bool:
    """
    إرسال عبر SendGrid API. يحتاج SENDGRID_API_KEY و SENDGRID_SENDER.
    يرجع True عند النجاح، False عند الفشل.
    """
    if not (_SENDGRID_KEY and _SENDGRID_SENDER and to):
        return False

    try:
        # استخدام REST API مباشرة (بدون حزمة sendgrid لتقليل الاعتمادات)
        import json, ssl, http.client
        payload = {
            "personalizations": [{
                "to": [{"email": to}],
                **({"cc": [{"email": x} for x in (cc or [])]} if cc else {}),
                **({"bcc": [{"email": x} for x in (bcc or [])]} if bcc else {}),
            }],
            "from": {"email": _SENDGRID_SENDER},
            **({"reply_to": {"email": reply_to}} if reply_to else {}),
            "subject": subject,
            "content": []
        }
        if text_body:
            payload["content"].append({"type": "text/plain; charset=utf-8", "value": text_body})
        payload["content"].append({"type": "text/html; charset=utf-8", "value": html_body})

        body = json.dumps(payload).encode("utf-8")
        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection("api.sendgrid.com", 443, context=context, timeout=20)
        try:
            conn.request(
                "POST", "/v3/mail/send", body=body,
                headers={
                    "Authorization": f"Bearer {_SENDGRID_KEY}",
                    "Content-Type": "application/json"
                }
            )
            resp = conn.getresponse()
            # SendGrid يعيد 202 عند القبول
            ok = (200 <= resp.status < 300)
        finally:
            conn.close()
        return ok
    except Exception:
        return False


# ====== SMTP (احتياطي/محلي) ======
def _send_via_smtp(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str],
    cc: Optional[Sequence[str]] = None,
    bcc: Optional[Sequence[str]] = None,
    reply_to: Optional[str] = None,
) -> bool:
    """
    إرسال عبر SMTP (يعمل محليًا؛ غالبًا محجوب على Render).
    يحتاج EMAIL_HOST/PORT/USER/PASS و EMAIL_USE_TLS.
    """
    host = os.getenv("EMAIL_HOST", "")
    port = int(os.getenv("EMAIL_PORT", "587") or "587")
    user = os.getenv("EMAIL_USER", "")
    pwd  = os.getenv("EMAIL_PASS", "")
    use_tls = str(os.getenv("EMAIL_USE_TLS", "True")).lower() in ("1", "true", "yes")
    if not (host and port and user and pwd and to):
        return False

    try:
        # إعداد الرسالة
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        if reply_to:
            msg.add_header("Reply-To", reply_to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        recipients = [to] + list(cc or []) + list(bcc or [])

        smtp = smtplib.SMTP(host, port, timeout=20)
        try:
            smtp.ehlo()
            if use_tls:
                try:
                    smtp.starttls()
                    smtp.ehlo()
                except Exception:
                    pass
            smtp.login(user, pwd)
            smtp.sendmail(user, recipients, msg.as_string())
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
        return True
    except Exception:
        return False


# ====== الدالة العامة المستخدمة في المشروع ======
def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    cc: Optional[Sequence[str]] = None,
    bcc: Optional[Sequence[str]] = None,
    reply_to: Optional[str] = None,
) -> bool:
    """
    نحاول SendGrid أولاً (للعمل على Render)، وإن لم تتوفر مفاتيحه نعود لـ SMTP.
    """
    # 1) جرّب SendGrid
    ok = _send_via_sendgrid(to, subject, html_body, text_body, cc, bcc, reply_to)
    if ok:
        return True
    # 2) جرّب SMTP محليًا
    return _send_via_smtp(to, subject, html_body, text_body, cc, bcc, reply_to)
