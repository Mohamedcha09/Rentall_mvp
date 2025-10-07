# app/payout_connect.py
import os
import stripe
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter()

def get_base_url(request: Request) -> str:
    """
    يحدد عنوان العودة لروابط Stripe.
    نعطي أولوية لـ CONNECT_REDIRECT_BASE إن وُجد، وإلا نستخلص الدومين الحالي.
    """
    env_base = (os.getenv("CONNECT_REDIRECT_BASE") or os.getenv("SITE_URL") or "").strip().rstrip("/")
    if env_base:
        # لو أعطيت SITE_URL مثل: https://m3ak.onrender.com
        return env_base
    # fallback آمن
    host = request.url.hostname or "localhost"
    return f"https://{host}"

def get_api_key_ok() -> tuple[bool, str]:
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    ok = key.startswith("sk_test_") or key.startswith("sk_live_")
    return ok, key


@router.api_route("/payout/connect/start", methods=["GET", "POST"])
def connect_start(request: Request, db: Session = Depends(get_db)):
    """
    نفس المسار يقبل GET و POST لتفادي 405.
    - ينشئ/يسترجع حساب Stripe Connect للمستخدم الحالي.
    - يُنشئ AccountLink ويُعيد توجيه المستخدم إلى Stripe لإكمال KYC.
    """
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    ok, key = get_api_key_ok()
    if not ok:
        return HTMLResponse(
            "<h3>Stripe: مفتاح غير مُهيّأ</h3>"
            "<p>ضبط STRIPE_SECRET_KEY بقيمة sk_test_ أو sk_live_ ثم أعد النشر.</p>",
            status_code=500
        )

    stripe.api_key = key
    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    try:
        # أنشئ حساب Express إن لم يوجد
        if not user.stripe_account_id:
            acct = stripe.Account.create(type="express")
            user.stripe_account_id = acct.id
            # مبدئيًا لا نعرف حالة payouts_enabled حتى يكمل KYC
            if hasattr(user, "payouts_enabled"):
                user.payouts_enabled = False
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
        # ارسل المستخدم إلى Stripe
        return RedirectResponse(url=link.url, status_code=303)

    except stripe.error.AuthenticationError:
        return HTMLResponse(
            "<h3>Stripe: Invalid API Key</h3>"
            "<p>المفتاح غير صحيح أو من وضع مختلف. استخدم مفاتيح وضع الاختبار "
            "(sk_test_/pk_test_) أو تأكد من مفاتيح الوضع الحي.</p>",
            status_code=401
        )
    except Exception as e:
        return HTMLResponse(f"<h3>Stripe Error</h3><pre>{str(e)}</pre>", status_code=500)


@router.get("/payout/connect/refresh")
def connect_refresh(request: Request, db: Session = Depends(get_db)):
    """
    يعود المستخدم من Stripe — نجلب حالة الحساب ونحدّث payouts_enabled إن وُجد العمود.
    """
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
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user)
            db.commit()
    except Exception:
        pass

    return RedirectResponse(url="/payout/settings", status_code=303)