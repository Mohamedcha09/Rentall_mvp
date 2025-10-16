# app/debug_email.py
import os, socket, ssl, smtplib, traceback
from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

try:
    from .emailer import send_email  # دالة الإرسال العادية
except Exception:
    def send_email(*args, **kwargs):
        return False

from .database import get_db
from .models import User

router = APIRouter(tags=["debug-email"])

def _me(request: Request, db: Session) -> User | None:
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    return db.get(User, uid) if uid else None

def _admin_only(u: User | None):
    if not u or (getattr(u, "role", "") or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="admin only")

@router.get("/admin/debug/email/env")
def email_env(request: Request, db: Session = Depends(get_db)):
    u = _me(request, db); _admin_only(u)
    return {
        "EMAIL_HOST": os.getenv("EMAIL_HOST"),
        "EMAIL_PORT": os.getenv("EMAIL_PORT"),
        "EMAIL_USER": os.getenv("EMAIL_USER"),
        "EMAIL_USE_TLS": os.getenv("EMAIL_USE_TLS"),
        "SITE_URL": os.getenv("SITE_URL"),
        "has_PASS": bool(os.getenv("EMAIL_PASS")),
    }

@router.get("/admin/debug/email/send")
def email_send(request: Request, db: Session = Depends(get_db), to: str | None = None):
    u = _me(request, db); _admin_only(u)
    to_addr = to or os.getenv("TEST_EMAIL_TO") or getattr(u, "email", None)
    if not to_addr:
        raise HTTPException(400, "no recipient (to or TEST_EMAIL_TO)")
    ok = send_email(to_addr, "RentAll — SMTP test", "<p>SMTP OK</p>", text_body="SMTP OK")
    return {"ok": ok, "to": to_addr}

@router.get("/admin/debug/email/diag")
def email_diag(request: Request, db: Session = Depends(get_db), to: str | None = None):
    """
    تشخيص خطوة بخطوة: DNS، اتصال، STARTTLS، LOGIN، SEND.
    يرجّع تقريرًا نصيًا يوضّح مكان العطل بالضبط.
    """
    u = _me(request, db); _admin_only(u)

    host = os.getenv("EMAIL_HOST")
    port = int(os.getenv("EMAIL_PORT") or "0")
    user = os.getenv("EMAIL_USER")
    pwd  = os.getenv("EMAIL_PASS")
    use_tls = str(os.getenv("EMAIL_USE_TLS") or "True").lower() in ("1","true","yes")
    to_addr = to or os.getenv("TEST_EMAIL_TO") or user

    report = []
    def log(line): report.append(line)

    try:
        log(f"[{datetime.utcnow().isoformat()}] DIAG START")
        log(f"HOST={host} PORT={port} USER={user} TLS={use_tls} has_PASS={bool(pwd)} to={to_addr}")

        if not all([host, port, user, pwd, to_addr]):
            log("!! Missing one or more required env vars.")
            return {"ok": False, "stage": "env", "report": report}

        # DNS resolve
        try:
            ip = socket.gethostbyname(host)
            log(f"DNS: {host} -> {ip}")
        except Exception as e:
            log(f"!! DNS resolve failed: {e}")
            return {"ok": False, "stage": "dns", "report": report}

        # اتصال عادي
        try:
            smtp = smtplib.SMTP(host, port, timeout=20)
            code, hello = smtp.ehlo()
            log(f"EHLO: {code} {hello!r}")
        except Exception as e:
            log(f"!! Connect/EHLO failed: {e}")
            return {"ok": False, "stage": "connect", "report": report}

        # STARTTLS
        try:
            if use_tls and port == 587:
                code = smtp.starttls(context=ssl.create_default_context())[0]
                log(f"STARTTLS: {code}")
                code, hello = smtp.ehlo()
                log(f"EHLO(after TLS): {code} {hello!r}")
            else:
                log("STARTTLS: skipped")
        except Exception as e:
            log(f"!! STARTTLS failed: {e}")
            try: smtp.quit()
            except: pass
            return {"ok": False, "stage": "starttls", "report": report}

        # LOGIN
        try:
            smtp.login(user, pwd)
            log("LOGIN: ok")
        except Exception as e:
            log(f"!! LOGIN failed: {e}")
            try: smtp.quit()
            except: pass
            return {"ok": False, "stage": "login", "report": report}

        # SEND
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "RentAll DIAG"
            msg["From"] = user
            msg["To"] = to_addr
            msg.attach(MIMEText("SMTP DIAG OK (text)", "plain", "utf-8"))
            msg.attach(MIMEText("<p>SMTP DIAG OK (html)</p>", "html", "utf-8"))
            smtp.sendmail(user, [to_addr], msg.as_string())
            log("SEND: ok")
            smtp.quit()
            log("QUIT: ok")
            return {"ok": True, "stage": "done", "report": report}
        except Exception as e:
            log(f"!! SEND failed: {e}\n{traceback.format_exc()}")
            try: smtp.quit()
            except: pass
            return {"ok": False, "stage": "send", "report": report}

    except Exception as e:
        log(f"!! UNEXPECTED: {e}\n{traceback.format_exc()}")
        return {"ok": False, "stage": "unexpected", "report": report}
