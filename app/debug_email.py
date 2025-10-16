# app/debug_email.py
import os
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

try:
    from .emailer import send_email
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
    ok = send_email(to_addr, "RentAll — PROD SMTP test", "<p>SMTP OK</p>", text_body="SMTP OK")
    return {"ok": ok, "to": to_addr}
