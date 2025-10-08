# app/payout_connect.py
import os
import stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter()

# ---------- Helpers ----------
def _base_url(request: Request) -> str:
    env_base = (os.getenv("CONNECT_REDIRECT_BASE") or os.getenv("SITE_URL") or "").strip().rstrip("/")
    if env_base:
        return env_base
    host = request.url.hostname or "localhost"
    scheme = "https"
    return f"{scheme}://{host}"

def _set_api_key_or_500():
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not (key.startswith("sk_test_") or key.startswith("sk_live_")):
        raise HTTPException(500, "STRIPE_SECRET_KEY missing/invalid (must start with sk_test_ or sk_live_)")
    stripe.api_key = key

# ---------- تشخيص سريع (يرجى إبقاؤه مؤقتًا) ----------
@router.get("/api/stripe/connect/debug")
def connect_debug(request: Request, db: Session = Depends(get_db)):
    """يعرض ما يراه السيرفر عن المستخدم الحالي للربط."""
    sess_user = request.session.get("user") or {}
    uid = sess_user.get("id")
    sess_acct = request.session.get("connect_account_id")
    db_user = db.query(User).get(uid) if uid else None
    db_acct = getattr(db_user, "stripe_account_id", None) if db_user else None
    return {
        "session_user_present": bool(uid),
        "session_connect_account_id": sess_acct,
        "db_user_present": bool(db_user is not None),
        "db_stripe_account_id": db_acct,
    }

# ---------- ابدأ الربط: ينشئ الحساب ويحفظه في DB + Session ثم يفتح Stripe ----------
@router.api_route("/payout/connect/start", methods=["GET", "POST"])
def payout_connect_start(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    acct_id = getattr(user, "stripe_account_id", None)
    if not acct_id:
        acct = stripe.Account.create(
            type="express",
            country="CA",
            email=(user.email or None),
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
        )
        acct_id = acct.id
        # ⬇️ حفظ فعلي في قاعدة البيانات
        try:
            user.stripe_account_id = acct_id
        except Exception:
            # لو العمود غير موجود في الموديل يرجّع خطأ—سنكشفه في /api/stripe/connect/debug
            pass
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = False
        db.add(user)
        db.commit()

    # خزّن أيضًا في الـSession (حتى لو الـDB ناقص عمود)
    request.session["connect_account_id"] = acct_id

    base = _base_url(request)
    link = stripe.AccountLink.create(
        account=acct_id,
        type="account_onboarding",
        refresh_url=f"{base}/payout/connect/refresh",
        return_url=f"{base}/payout/settings?done=1",
    )
    return RedirectResponse(link.url, status_code=303)

# ---------- فتح Onboarding لو عندك acct في الـSession/DB ----------
@router.get("/connect/onboard")
def connect_onboard(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    acct_id = request.session.get("connect_account_id")
    if not acct_id:
        user = db.query(User).get(sess["id"])
        if user and getattr(user, "stripe_account_id", None):
            acct_id = user.stripe_account_id
            request.session["connect_account_id"] = acct_id
    if not acct_id:
        return RedirectResponse(url="/payout/connect/start", status_code=303)

    base = _base_url(request)
    link = stripe.AccountLink.create(
        account=acct_id,
        type="account_onboarding",
        refresh_url=f"{base}/payout/connect/refresh",
        return_url=f"{base}/payout/settings?done=1",
    )
    return RedirectResponse(link.url)

# ---------- Refresh ----------
@router.get("/payout/connect/refresh")
def payout_connect_refresh(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)
    user = db.query(User).get(sess["id"])
    if not user or not getattr(user, "stripe_account_id", None):
        return RedirectResponse(url="/payout/settings", status_code=303)
    try:
        acct = stripe.Account.retrieve(user.stripe_account_id)
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user)
            db.commit()
    except Exception:
        pass
    return RedirectResponse(url="/payout/settings", status_code=303)

# ---------- حالة الحساب ----------
@router.get("/api/stripe/connect/status")
def stripe_connect_status(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return JSONResponse({"connected": False, "payouts_enabled": False, "reason": "unauthenticated"}, status_code=401)

    user = db.query(User).get(sess["id"])
    if not user:
        return JSONResponse({"connected": False, "payouts_enabled": False, "reason": "user_not_found"}, status_code=404)

    acct_id = getattr(user, "stripe_account_id", None) or request.session.get("connect_account_id")
    if not acct_id:
        return JSONResponse({"connected": False, "payouts_enabled": False, "reason": "no_account"})

    acct = stripe.Account.retrieve(acct_id)
    return JSONResponse({
        "connected": True,
        "account_id": acct.id,
        "charges_enabled": bool(acct.charges_enabled),
        "payouts_enabled": bool(acct.payouts_enabled),
        "details_submitted": bool(acct.details_submitted),
        "requirements_due": acct.get("requirements", {}).get("currently_due", []),
    })