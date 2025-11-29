from __future__ import annotations
import os
import smtplib
from typing import Optional, Iterable, Union, List
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

# =========================
# SMTP Settings (Namecheap Private Email)
# =========================
SMTP_HOST = os.getenv("SMTP_HOST", "mail.privateemail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "")
FROM_NAME  = os.getenv("FROM_NAME", "Sevor Notifications")

def _normalize_list(value: Optional[Union[str, Iterable[str]]]) -> List[str]:
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

    if not SMTP_USER or not SMTP_PASSWORD:
        print("[email_service] ❌ SMTP credentials missing")
        return False

    recipients = _normalize_list(to)
    if not recipients:
        print("[email_service] ⚠️ No recipient")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = ", ".join(recipients)

    if cc:
        cc_list = _normalize_list(cc)
        msg["Cc"] = ", ".join(cc_list)
    else:
        cc_list = []

    if reply_to:
        msg["Reply-To"] = reply_to

    msg.attach(MIMEText(text_body or "", "plain"))
    msg.attach(MIMEText(html_body or "", "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(
                FROM_EMAIL,
                recipients + cc_list + _normalize_list(bcc),
                msg.as_string(),
            )
            print(f"[email_service] ✅ Email sent to {recipients}")
            return True

    except Exception as e:
        print(f"[email_service] ❌ SMTP error: {e}")
        return False


# Optional test
if __name__ == "__main__":
    ok = send_email(
        to=FROM_EMAIL,
        subject="SMTP TEST — Sevor",
        html_body="<h2>SMTP is working 🎉</h2>",
        text_body="SMTP works"
    )
    print("Test send:", ok)
