# app/payout_connect.py
import os
import stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter()

# =========================
# Helpers
# =========================
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

def _ensure_account(db: Session, user: User) -> str:
    """
    ينشئ حساب Express إذا غير موجود و يحفظه في DB وSession.
    يعيد acct_id
    """
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
        try:
            user.stripe_account_id = acct_id
        except Exception:
            pass
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
        db.add(user)
        db.commit()
    return acct_id

def _pct(amount_cents: int, fee_pct: float) -> int:
    return int(round(amount_cents * (float(fee_pct) / 100.0)))


# =========================
# Debug
# =========================
@router.get("/api/stripe/connect/debug")
def connect_debug(request: Request, db: Session = Depends(get_db)):
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


# =========================
# Start / Onboard / Refresh
# =========================
@router.api_route("/payout/connect/start", methods=["GET","POST"])
def payout_connect_start(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    acct_id = _ensure_account(db, user)
    request.session["connect_account_id"] = acct_id

    base = _base_url(request)
    link = stripe.AccountLink.create(
        account=acct_id,
        type="account_onboarding",
        refresh_url=f"{base}/payout/connect/refresh",
        return_url=f"{base}/payout/settings?done=1",
    )
    return RedirectResponse(link.url, status_code=303)


@router.get("/connect/onboard")
def connect_onboard(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    acct_id = request.session.get("connect_account_id") or getattr(user, "stripe_account_id", None)
    if not acct_id:
        acct_id = _ensure_account(db, user)
        request.session["connect_account_id"] = acct_id

    base = _base_url(request)
    link = stripe.AccountLink.create(
        account=acct_id,
        type="account_onboarding",
        refresh_url=f"{base}/payout/connect/refresh",
        return_url=f"{base}/payout/settings?done=1",
    )
    return RedirectResponse(link.url)


@router.get("/payout/connect/refresh")
def payout_connect_refresh(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)
    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/payout/settings", status_code=303)
    try:
        if getattr(user, "stripe_account_id", None):
            acct = stripe.Account.retrieve(user.stripe_account_id)
            # مزامنة DB
            try:
                if getattr(user, "stripe_account_id", None) != acct.id:
                    user.stripe_account_id = acct.id
            except Exception:
                pass
            if hasattr(user, "payouts_enabled"):
                user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user); db.commit()
    except Exception:
        pass
    return RedirectResponse(url="/payout/settings", status_code=303)


# =========================
# Status + Force Save
# =========================
@router.get("/api/stripe/connect/status")
def stripe_connect_status(request: Request, db: Session = Depends(get_db), autocreate: int = 0):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return JSONResponse({"connected": False, "payouts_enabled": False, "reason": "unauthenticated"}, status_code=401)

    user = db.query(User).get(sess["id"])
    if not user:
        return JSONResponse({"connected": False, "payouts_enabled": False, "reason": "user_not_found"}, status_code=404)

    acct_id = getattr(user, "stripe_account_id", None) or request.session.get("connect_account_id")

    if not acct_id and autocreate:
        acct_id = _ensure_account(db, user)
        request.session["connect_account_id"] = acct_id

    if not acct_id:
        return JSONResponse({"connected": False, "payouts_enabled": False, "reason": "no_account"})

    acct = stripe.Account.retrieve(acct_id)

    # حفظ تلقائي للـID و payouts_enabled في DB
    changed = False
    if getattr(user, "stripe_account_id", None) != acct.id:
        try:
            user.stripe_account_id = acct.id
            changed = True
        except Exception:
            pass
    if hasattr(user, "payouts_enabled"):
        pe = bool(getattr(acct, "payouts_enabled", False))
        if user.payouts_enabled != pe:
            user.payouts_enabled = pe
            changed = True
    if changed:
        db.add(user); db.commit()

    return JSONResponse({
        "connected": True,
        "account_id": acct.id,
        "charges_enabled": bool(acct.charges_enabled),
        "payouts_enabled": bool(acct.payouts_enabled),
        "details_submitted": bool(acct.details_submitted),
        "capabilities": getattr(acct, "capabilities", None),
        "requirements_due": acct.get("requirements", {}).get("currently_due", []),
    })


@router.post("/api/stripe/connect/save")
def stripe_connect_force_save(request: Request, db: Session = Depends(get_db)):
    """
    حفظ إجباري للـ account_id إلى DB من الـSession/Stripe
    """
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        raise HTTPException(401, "unauthenticated")

    user = db.query(User).get(sess["id"])
    if not user:
        raise HTTPException(404, "user_not_found")

    acct_id = request.session.get("connect_account_id") or getattr(user, "stripe_account_id", None)
    if not acct_id:
        raise HTTPException(400, "no_account")

    acct = stripe.Account.retrieve(acct_id)

    try:
        user.stripe_account_id = acct.id
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
        db.add(user); db.commit()
    except Exception:
        pass

    return {"saved": True, "account_id": acct.id}


# =========================
# Split Test (Destination charge)
# =========================
@router.get("/split/test")
def split_test_checkout(
    request: Request,
    db: Session = Depends(get_db),
    amount: int = 2000,          # 2000 = 20.00
    currency: str | None = None,
):
    """
    تجربة دفع مع تقسيم المبلغ:
    - Destination charge إلى حساب المستخدم المتصل + عمولة المنصة application_fee_amount
    """
    _set_api_key_or_500()
    sess_user = request.session.get("user")
    if not sess_user:
        return RedirectResponse("/login", status_code=303)

    user = db.query(User).get(sess_user["id"])
    if not user or not getattr(user, "stripe_account_id", None):
        return JSONResponse({"error": "no_connected_account"}, status_code=400)

    acct_id = user.stripe_account_id
    acct = stripe.Account.retrieve(acct_id)
    if not bool(getattr(acct, "charges_enabled", False)):
        return JSONResponse({"error": "charges_enabled=false; complete onboarding first"}, status_code=400)

    cur     = (currency or os.getenv("CURRENCY") or "cad").lower()
    fee_pct = float(os.getenv("PLATFORM_FEE_PCT") or 10)
    app_fee = _pct(amount, fee_pct)

    base = _base_url(request)
    success = f"{base}/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel  = f"{base}/cancel"

    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=success,
        cancel_url=cancel,
        line_items=[{
            "price_data": {
                "currency": cur,
                "product_data": {"name": "Test split order"},
                "unit_amount": amount,
            },
            "quantity": 1,
        }],
        payment_intent_data={
            "application_fee_amount": app_fee,
            "transfer_data": {"destination": acct_id},
        },
        metadata={"split_mode": "destination_charge", "acct": acct_id, "fee_pct": str(fee_pct)},
    )
    return RedirectResponse(session.url, status_code=303)