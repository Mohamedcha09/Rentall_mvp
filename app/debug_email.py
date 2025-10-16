# app/debug_email.py
import os, traceback
from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from .email_service import send_email   # ✅ استخدام SendGrid
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
    """إظهار متغيرات SendGrid الأساسية."""
    u = _me(request, db); _admin_only(u)
    return {
        "SENDGRID_API_KEY": bool(os.getenv("SENDGRID_API_KEY")),
        "FROM_EMAIL": os.getenv("FROM_EMAIL"),
        "SITE_URL": os.getenv("SITE_URL") or os.getenv("BASE_URL"),
    }

@router.get("/admin/debug/email/send")
def email_send(request: Request, db: Session = Depends(get_db), to: str | None = None):
    """إرسال رسالة تجريبية عبر SendGrid."""
    u = _me(request, db); _admin_only(u)
    to_addr = (to or os.getenv("TEST_EMAIL_TO") or getattr(u, "email", None))
    if not to_addr:
        raise HTTPException(400, "no recipient (to or TEST_EMAIL_TO)")

    html = "<p>SendGrid test — OK</p>"
    ok = send_email(to_addr, "RentAll — SendGrid test", html, text_body="SendGrid test — OK")
    return {"ok": bool(ok), "to": to_addr, "via": "sendgrid"}

# (اختياري) إذا أردت إبقاء تشخيص SMTP القديم فاحذف الاستيرادات الخاصة به
# أو اتركه لكن لا تعتمد عليه لأن الإرسال صار عبر SendGrid الآن.
