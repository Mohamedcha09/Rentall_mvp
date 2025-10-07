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
    # استخدم متغير البيئة إن وُجد، وإلا خُذ من الطلب
    env_base = os.getenv("CONNECT_REDIRECT_BASE", "").strip().rstrip("/")
    if env_base:
        return env_base
    # Render يكون دومينه https
    host = request.url.hostname or "localhost"
    return f"https://{host}"

def get_api_key_ok() -> tuple[bool, str]:
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    ok = key.startswith("sk_test_") or key.startswith("sk_live_")
    return ok, key

@router.post("/payout/connect")
def connect_post_redirect():
    """
    دعم فورم قديم يرسل POST إلى /payout/connect
    نحوله إلى /payout/connect/start
    """
    return RedirectResponse(url="/payout/connect/start", status_code=303)

# 👇 أهم تعديل: نقبل GET و POST لنفس المسار لتفادي 405
@router.api_route("/payout/connect/start", methods=["GET", "POST"])
def connect_start(request: Request, db: Session = Depends(get_db)):
    """
    يبدأ رحلة Stripe Connect:
      - ينشئ حساب Express للمستخدم إن لم يكن موجودًا
      - يولّد AccountLink ويعيد توجيه المتصفح إلى Stripe
    """
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    ok, key = get_api_key_ok()
    if not ok:
        return HTMLResponse(
            "<h3>Stripe: مفتاح غير مُهيّأ</h3>"
            "<p>ضبط STRIPE_SECRET_KEY (sk_test_ أو sk_live_) ثم أعد النشر.</p>",
            status_code=500
        )

    stripe.api_key = key
    # get() قد يطلق تحذير قديم، لكن يعمل. بديله: db.get(User, sess['id']) في SQLAlchemy 2.x
    user = db.query(User).get(sess["id"]) or db.get(User, sess["id"])

    try:
        # أنشئ حساب للمستخدم إن لم يكن موجوداً
        if not getattr(user, "stripe_account_id", None):
            acct = stripe.Account.create(type="express")
            user.stripe_account_id = acct.id
            # إذا لديك عمود payouts_enabled نضبطه على False كبداية
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
        return RedirectResponse(url=link.url, status_code=303)

    except stripe.error.AuthenticationError:
        return HTMLResponse(
            "<h3>Stripe: Invalid API Key</h3>"
            "<p>المفتاح غير صحيح أو من وضع مختلف. استخدم مفاتيح Test أو Live الصحيحة.</p>",
            status_code=401
        )
    except Exception as e:
        return HTMLResponse(f"<h3>Stripe Error</h3><pre>{str(e)}</pre>", status_code=500)


@router.get("/payout/connect/refresh")
def connect_refresh(request: Request, db: Session = Depends(get_db)):
    """
    يجلب حالة الحساب من Stripe ويحدّث users.payouts_enabled ثم يعيدك لإعدادات التحويل.
    """
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    ok, key = get_api_key_ok()
    if not ok:
        return HTMLResponse("STRIPE_SECRET_KEY مفقود/غير صحيح.", status_code=500)

    stripe.api_key = key
    user = db.query(User).get(sess["id"]) or db.get(User, sess["id"])
    if not user or not getattr(user, "stripe_account_id", None):
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