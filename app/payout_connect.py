# app/payout_connect.py
import os
import stripe
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter()

def get_base_url(request: Request) -> str:
    # استخدم متغير البيئة إن وُجد، وإلا خُذ من الطلب
    env_base = os.getenv("CONNECT_REDIRECT_BASE", "").strip().rstrip("/")
    if env_base:
        return env_base
    # request.base_url قد تكون http داخليًا؛ نضبطها على https للنشر
    # Render يستخدم https على الدومين العام
    return f"https://{request.url.hostname}"

def get_api_key_ok() -> tuple[bool, str]:
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    ok = key.startswith("sk_test_") or key.startswith("sk_live_")
    return ok, key

@router.post("/payout/connect")
def connect_post_redirect():
    # دعم الفورم القديم في القالب
    return RedirectResponse(url="/payout/connect/start", status_code=303)

@router.get("/payout/connect/start")
def connect_start(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    ok, key = get_api_key_ok()
    if not ok:
        return HTMLResponse(
            "<h3>Stripe: مفتاح غير مُهيّأ</h3>"
            "<p>رجاءً ضبط STRIPE_SECRET_KEY بقيمة صحيحة (اختبار sk_test_ أو حيّ sk_live_) في Render ثم إعادة النشر.</p>",
            status_code=500
        )

    stripe.api_key = key
    user = db.query(User).get(sess["id"])

    try:
        # أنشئ حساب Express للمستخدم إن لم يكن موجوداً
        if not user.stripe_account_id:
            acct = stripe.Account.create(type="express")
            user.stripe_account_id = acct.id
            db.add(user)
            db.commit()
        else:
            acct = stripe.Account.retrieve(user.stripe_account_id)

        base = get_base_url(request)
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
            "<p>المفتاح غير صحيح أو من وضع مختلف. استخدم مفاتيح <strong>Test mode</strong> "
            "(sk_test_ و pk_test_) أو تأكد من صحة مفاتيح Live.</p>",
            status_code=401
        )
    except Exception as e:
        return HTMLResponse(f"<h3>Stripe Error</h3><pre>{str(e)}</pre>", status_code=500)

@router.get("/payout/connect/refresh")
def connect_refresh(request: Request, db: Session = Depends(get_db)):
    """يعيد جلب حالة الحساب من Stripe وتحديث payouts_enabled ثم يرجع لإعدادات التحويل."""
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    ok, key = get_api_key_ok()
    if not ok:
        return HTMLResponse("STRIPE_SECRET_KEY مفقود/غير صحيح.", status_code=500)

    stripe.api_key = key
    user = db.query(User).get(sess["id"])
    if not user or not user.stripe_account_id:
        return RedirectResponse(url="/payout/settings", status_code=303)

    try:
        acct = stripe.Account.retrieve(user.stripe_account_id)
        # لو عندك عمود payouts_enabled في جدول users، حدّثه
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user)
            db.commit()
    except Exception:
        pass

    return RedirectResponse(url="/payout/settings", status_code=303)
