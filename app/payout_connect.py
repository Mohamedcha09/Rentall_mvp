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
    env_base = (os.getenv("CONNECT_REDIRECT_BASE") or os.getenv("SITE_URL") or "").strip().rstrip("/")
    if env_base:
        return env_base
    host = request.url.hostname or "localhost"
    scheme = "https"
    return f"{scheme}://{host}"

def _api_key():
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    return (key.startswith("sk_test_") or key.startswith("sk_live_")), key

# يدعم GET و POST لتجنّب 405
@router.api_route("/payout/connect/start", methods=["GET", "POST"])
def payout_connect_start(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    ok, key = _api_key()
    if not ok:
        return HTMLResponse(
            "<h3>Stripe: مفتاح غير مُهيّأ</h3>"
            "<p>ضع STRIPE_SECRET_KEY (sk_test_ أو sk_live_) ثم أعد النشر.</p>",
            status_code=500
        )

    stripe.api_key = key
    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    try:
        # إنشاء حساب Express إذا لم يوجد
        if not user.stripe_account_id:
            acct = stripe.Account.create(type="express")
            user.stripe_account_id = acct.id
            if hasattr(user, "payouts_enabled"):
                user.payouts_enabled = False
            db.add(user)
            db.commit()
        else:
            acct = stripe.Account.retrieve(user.stripe_account_id)

        base = _base_url(request)
        link = stripe.AccountLink.create(
            account=acct.id,
            refresh_url=f"{base}/payout/connect/refresh",
            return_url=f"{base}/payout/settings",
            type="account_onboarding",
        )
        return RedirectResponse(url=link.url, status_code=303)

    except stripe.error.AuthenticationError:
        return HTMLResponse(
            "<h3>Stripe: Invalid API Key</h3>"
            "<p>تأكّد من مفاتيح الاختبار pk_test/sk_test أو مفاتيح Live.</p>",
            status_code=401
        )
    except Exception as e:
        return HTMLResponse(f"<h3>Stripe Error</h3><pre>{e}</pre>", status_code=500)

# مسارات مساعدة توجه دائمًا إلى start
@router.get("/payout/connect")
def payout_connect_alias_get():
    return RedirectResponse(url="/payout/connect/start", status_code=303)

@router.post("/payout/connect")
def payout_connect_alias_post():
    return RedirectResponse(url="/payout/connect/start", status_code=303)

@router.get("/payout/connect/refresh")
def payout_connect_refresh(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    ok, key = _api_key()
    if not ok:
        return HTMLResponse("STRIPE_SECRET_KEY مفقود/غير صحيح.", status_code=500)

    stripe.api_key = key
    user = db.query(User).get(sess["id"])
    if not user or not user.stripe_account_id:
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