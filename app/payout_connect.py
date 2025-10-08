# app/payout_connect.py
import os
import stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter()

# -----------------------------
# Helpers
# -----------------------------
def _base_url(request: Request) -> str:
    env_base = (os.getenv("CONNECT_REDIRECT_BASE") or os.getenv("SITE_URL") or "").strip().rstrip("/")
    if env_base:
        return env_base
    host = request.url.hostname or "localhost"
    scheme = "https"
    return f"{scheme}://{host}"

def _api_key() -> tuple[bool, str]:
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    return (key.startswith("sk_test_") or key.startswith("sk_live_")), key

def _set_api_key_or_500():
    ok, key = _api_key()
    if not ok:
        raise HTTPException(
            status_code=500,
            detail="STRIPE_SECRET_KEY is missing/invalid (must start with sk_test_ or sk_live_).",
        )
    stripe.api_key = key

# -----------------------------
# 0) Route توافقية للسابق: /payout/connect/start
#    تضمن إنشاء الحساب ثم ترسلك مباشرة للـ Onboarding
# -----------------------------
@router.api_route("/payout/connect/start", methods=["GET", "POST"])
def payout_connect_start(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # 1) أنشئ/احصل على الحساب المتصل واحفظه في DB + Session
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
        user.stripe_account_id = acct_id
        # اختياري: علَم محلي حتى يكتمل KYC
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = False
        db.add(user)
        db.commit()

    request.session["connect_account_id"] = acct_id  # ✅ نخزن في Session أيضًا

    # 2) وجّه للـ Onboarding
    base = _base_url(request)
    link = stripe.AccountLink.create(
        account=acct_id,
        type="account_onboarding",
        refresh_url=f"{base}/payout/connect/refresh",
        return_url=f"{base}/payout/settings?done=1",
    )
    return RedirectResponse(url=link.url, status_code=303)

# -----------------------------
# 1) بدء الربط (نسخة صريحة تحفظ في Session فقط وتُرجع JSON)
#    مفيدة لو بدك تشغّلها AJAX قبل فتح الـ Onboarding
# -----------------------------
@router.post("/connect/start")
def connect_start(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    user = db.query(User).get(sess["id"])
    if not user:
        return JSONResponse({"error": "user_not_found"}, status_code=404)

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
        user.stripe_account_id = acct_id
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = False
        db.add(user)
        db.commit()

    request.session["connect_account_id"] = acct_id
    return {"ok": True, "account_id": acct_id}

# -----------------------------
# 2) فتح صفحة Onboarding للحساب الموجود في Session
# -----------------------------
@router.get("/connect/onboard")
def connect_onboard(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    # لو مش موجود بالجلسة، حاول نسحبه من DB (يحدث أحيانًا بعد إعادة التشغيل)
    acct_id = request.session.get("connect_account_id")
    if not acct_id:
        user = db.query(User).get(sess["id"])
        if user and getattr(user, "stripe_account_id", None):
            acct_id = user.stripe_account_id
            request.session["connect_account_id"] = acct_id

    if not acct_id:
        # ارجعه لبدء الربط
        return RedirectResponse(url="/payout/connect/start", status_code=303)

    base = _base_url(request)
    link = stripe.AccountLink.create(
        account=acct_id,
        type="account_onboarding",
        refresh_url=f"{base}/payout/connect/refresh",
        return_url=f"{base}/payout/settings?done=1",
    )
    return RedirectResponse(link.url)

# -----------------------------
# 3) Refresh (لو المستخدم ضغط حاول مجددًا داخل Stripe)
# -----------------------------
@router.get("/payout/connect/refresh")
def payout_connect_refresh(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    if not user or not getattr(user, "stripe_account_id", None):
        return RedirectResponse(url="/payout/settings", status_code=303)

    # مزامنة بسيطة للحقل المحلي
    try:
        acct = stripe.Account.retrieve(user.stripe_account_id)
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user)
            db.commit()
    except Exception:
        pass

    return RedirectResponse(url="/payout/settings", status_code=303)

# -----------------------------
# 4) API حالة الحساب المتصل (تعرض المطلوب أيضاً)
# -----------------------------
@router.get("/api/stripe/connect/status")
def stripe_connect_status(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    user = db.query(User).get(sess["id"])
    if not user:
        return JSONResponse({"error": "user_not_found"}, status_code=404)

    acct_id = getattr(user, "stripe_account_id", None) or request.session.get("connect_account_id")
    if not acct_id:
        return JSONResponse({
            "has_account": False,
            "account_id": None,
            "payouts_enabled": False,
            "charges_enabled": False,
            "details_submitted": False,
            "requirements_due": ["create_account_via_/connect/start"]
        })

    acct = stripe.Account.retrieve(acct_id)
    payouts_enabled   = bool(getattr(acct, "payouts_enabled", False))
    charges_enabled   = bool(getattr(acct, "charges_enabled", False))
    details_submitted = bool(getattr(acct, "details_submitted", False))
    requirements_due  = acct.get("requirements", {}).get("currently_due", [])

    # مزامنة محلية اختيارية
    if hasattr(user, "payouts_enabled") and user.payouts_enabled != payouts_enabled:
        user.payouts_enabled = payouts_enabled
        db.add(user)
        db.commit()

    return JSONResponse({
        "has_account": True,
        "account_id": acct.id,
        "payouts_enabled": payouts_enabled,
        "charges_enabled": charges_enabled,
        "details_submitted": details_submitted,
        "requirements_due": requirements_due,
    })