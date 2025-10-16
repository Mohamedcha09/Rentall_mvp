# app/emailer.py
from __future__ import annotations
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Iterable, Tuple

def _as_bool(v: str | None, default: bool = True) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")

def _from_header() -> str:
    user = os.getenv("EMAIL_USER", "") or "no-reply@example.com"
    name = os.getenv("EMAIL_FROM_NAME", "") or "Rentall"
    # إن كان اسم العرض فارغًا نرجع البريد فقط
    return f"{name} <{user}>" if name else user

def send_email(
    to: str | Iterable[str],
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    cc: Optional[Iterable[str]] = None,
    bcc: Optional[Iterable[str]] = None,
    attachments: Optional[Iterable[Tuple[str, bytes, str]]] = None,  # (filename, content_bytes, mime)
) -> bool:
    """
    يرسل بريد HTML (+نصي احتياطي) عبر SMTP.
    يعتمد على المتغيرات:
      - EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS
      - EMAIL_USE_TLS (افتراضي True)
      - EMAIL_FROM_NAME (اختياري)
    يعيد True عند نجاح الإرسال. لا يرمي استثناءات (يعود False عند الفشل).
    """
    try:
        host = os.getenv("EMAIL_HOST", "")
        port = int(os.getenv("EMAIL_PORT", "587"))
        user = os.getenv("EMAIL_USER", "")
        pwd  = os.getenv("EMAIL_PASS", "")
        use_tls = _as_bool(os.getenv("EMAIL_USE_TLS", "true"), True)

        if not (host and port and user and pwd):
            return False

        # تأكد أن to عبارة عن قائمة
        if isinstance(to, str):
            to_list = [to]
        else:
            to_list = list(to or [])

        if not to_list:
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = _from_header()
        msg["To"] = ", ".join(to_list)
        if cc:
            cc_list = list(cc)
            if cc_list:
                msg["Cc"] = ", ".join(cc_list)
        else:
            cc_list = []

        # النص الاحتياطي
        if not text_body:
            try:
                # تحويل بسيط من HTML إلى نص
                import re
                txt = html_body
                txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.I)
                txt = re.sub(r"</p\s*>", "\n\n", txt, flags=re.I)
                txt = re.sub(r"<[^>]+>", "", txt)
                text_body = txt.strip()
            except Exception:
                text_body = " "

        # أجزاء المحتوى
        part_text = MIMEText(text_body or " ", "plain", _charset="utf-8")
        part_html = MIMEText(html_body or " ", "html", _charset="utf-8")
        msg.attach(part_text)
        msg.attach(part_html)

        # مرفقات (اختياري)
        if attachments:
            from email.mime.base import MIMEBase
            from email import encoders
            for filename, content_bytes, mime in attachments:
                main_type, sub_type = (mime.split("/", 1) + ["octet-stream"])[:2]
                part = MIMEBase(main_type, sub_type)
                part.set_payload(content_bytes or b"")
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                msg.attach(part)

        # الإرسال
        smtp = smtplib.SMTP(host, port, timeout=30)
        try:
            if use_tls:
                smtp.starttls()
            smtp.login(user, pwd)
            all_rcpts = to_list + cc_list + (list(bcc or []) if bcc else [])
            smtp.sendmail(user, all_rcpts, msg.as_string())
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
        return True
    except Exception:
        # لا نكسر التدفق — نعطي False فقط
        return False