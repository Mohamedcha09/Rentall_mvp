# app/payout_connect.py
import os
import stripe
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter()

def _base_url(request: Request) -> str:
    env_base = (os.getenv("CONNECT_REDIRECT_BASE") or "").strip().rstrip("/")
    if env_base:
        return env_base
    host = request.url.hostname or "localhost"
    return f"https://{host}"

def _api_key() -> tuple[bool, str]:
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    return (key.startswith("sk_test_") or key.startswith("sk_live_")), key

def _connect_start_impl(request: Request, db: Session):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    ok, key = _api_key()
    if not ok:
        return HTMLResponse(
            "<h3>Stripe: مفتاح غير مُهيّأ</h3>"
            "<p>اضبط STRIPE_SECRET_KEY (sk_test_ أو sk_live_) ثم أعد النشر.</p>",
            status_code=500
        )

    stripe.api_key = key
    user = db.query(User).get(sess["id"]) or db.get(User, sess["id"])

    try:
        if not getattr(user, "stripe_account_id", None):
            acct = stripe.Account.create(type="express")
            user.stripe_account_id = acct.id
            if hasattr(user, "payouts_enabled"):
                user.payouts_enabled = False
            db.add(user)
            db.commit()
        else:
            acct = stripe.Account.retrieve(user.stripe_account_id)

        link = stripe.AccountLink.create(
            account=acct.id,
            refresh_url=f"{_base_url(request)}/payout/connect/refresh",
            return_url=f"{_base_url(request)}/payout/settings",
            type="account_onboarding",
        )
        return RedirectResponse(url=link.url, status_code=303)

    except stripe.error.AuthenticationError:
        return HTMLResponse(
            "<h3>Stripe: Invalid API Key</h3>"
            "<p>المفتاح غير صحيح أو من وضع مختلف (Test/Live).</p>",
            status_code=401
        )
    except Exception as e:
        return HTMLResponse(f"<h3>Stripe Error</h3><pre>{str(e)}</pre>", status_code=500)

@router.post("/payout/connect")
def connect_post_redirect():
    return RedirectResponse(url="/payout/connect/start", status_code=303)

# نُعرّف طريقتين منفصلتين (GET و POST) ليتفادى الخادم 405 تمامًا
@router.get("/payout/connect/start")
def connect_start_get(request: Request, db: Session = Depends(get_db)):
    return _connect_start_impl(request, db)

@router.post("/payout/connect/start")
def connect_start_post(request: Request, db: Session = Depends(get_db)):
    return _connect_start_impl(request, db)

@router.get("/payout/connect/refresh")
def connect_refresh(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    ok, key = _api_key()
    if not ok:
        return HTMLResponse("STRIPE_SECRET_KEY مفقود/غير صحيح.", status_code=500)

    stripe.api_key = key
    user = db.query(User).get(sess["id"]) or db.get(User, sess["id"])
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