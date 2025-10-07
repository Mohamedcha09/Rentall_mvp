# app/payout_routes.py
import os
from typing import Optional

import stripe
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter(tags=["payouts"])

# ===== Helpers =====
def _require_login(request: Request) -> Optional[dict]:
    return request.session.get("user")

def _stripe_key_ok() -> bool:
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    return key.startswith("sk_test_") or key.startswith("sk_live_")

def _refresh_connect_status(db: Session, user: User) -> None:
    """
    يُحدّث حالة payouts_enabled من Stripe للحساب المرتبط بالمستخدم.
    يُستدعى عند الرجوع من Stripe (return/refresh).
    """
    if not user or not user.stripe_account_id:
        return
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    if not key:
        return
    try:
        stripe.api_key = key
        acct = stripe.Account.retrieve(user.stripe_account_id)
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user)
            db.commit()
    except Exception:
        # نتجاهل الخطأ بهدوء — الصفحة ستعرض للمستخدم أنه لم يكتمل الربط
        pass


# ===== 1) صفحة إعدادات التحويل للمالك =====
@router.get("/payout/settings")
def payout_settings(request: Request, db: Session = Depends(get_db)):
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    db_user = db.query(User).get(sess["id"])
    if not db_user:
        return RedirectResponse(url="/login", status_code=303)

    ctx = {
        "request": request,
        "title": "إعدادات التحويل (Stripe Connect)",
        "session_user": request.session.get("user"),
        "has_api_key": _stripe_key_ok(),
        "stripe_account_id": getattr(db_user, "stripe_account_id", None),
        "payouts_enabled": bool(getattr(db_user, "payouts_enabled", False)),
    }
    return request.app.templates.TemplateResponse("payout_settings.html", ctx)


# ===== 2) زر "ابدأ الربط" (يحوّل لمسار pay_api) =====
@router.post("/payout/connect/start")
def payout_connect_start_proxy(request: Request):
    """
    هذا مجرد Proxy لتسهيل الاستدعاء من القالب.
    سيحوّل مباشرة إلى مسار Stripe الذي بداخل pay_api.py
    """
    return RedirectResponse(url="/api/stripe/connect/start", status_code=303)


# ===== 3) مسارات العودة/التحديث من Stripe (تتوافق مع pay_api.py) =====
@router.get("/payouts/return")
def payouts_return(request: Request, db: Session = Depends(get_db)):
    """
    Stripe يعود إلى هذا المسار بعد إكمال الـ Onboarding.
    نحدّث حالة الحساب محليًا ثم نعيد المالك إلى صفحة الإعدادات.
    """
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    db_user = db.query(User).get(sess["id"])
    _refresh_connect_status(db, db_user)

    # نعيده للصفحة (ستعرض الحالة المحدثة)
    return RedirectResponse(url="/payout/settings", status_code=303)


@router.get("/payouts/refresh")
def payouts_refresh(request: Request, db: Session = Depends(get_db)):
    """
    Stripe يستدعي هذا عند الضغط على "رجوع" أثناء عملية Onboarding.
    نعيد المستخدم لصفحة الإعدادات ونحاول تحديث الحالة.
    """
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    db_user = db.query(User).get(sess["id"])
    _refresh_connect_status(db, db_user)

    return RedirectResponse(url="/payout/settings", status_code=303)


# ===== 4) فحص صحة إعداد المفتاح (اختياري لعرض رسالة مفيدة) =====
@router.get("/payout/debug-key")
def payout_debug_key():
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    if not key:
        return HTMLResponse("<h4>STRIPE_SECRET_KEY غير مضبوط</h4>", status_code=500)
    mode = "TEST" if key.startswith("sk_test_") else ("LIVE" if key.startswith("sk_live_") else "UNKNOWN")
    return HTMLResponse(f"<pre>Stripe key is set.\nMode: {mode}\nValue (masked): {key[:8]}...{key[-4:]}</pre>")