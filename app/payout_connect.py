# app/payout_connect.py
import os
import stripe
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
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
        if not getattr(user, "stripe_account_id", None):
            acct = stripe.Account.create(type="express")
            user.stripe_account_id = acct.id
            # افتراضياً نعطّل حتى يكتمل KYC
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
    """
    يُستدعى إذا ضغط المستخدم "حاول مجددًا" في Stripe.
    يُعيده لصفحة الإعداد بعد محاولة مزامنة سريعة.
    """
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
        # حفظ العلم في الجدول (اختياري إن كان العمود موجوداً)
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user)
            db.commit()
    except Exception:
        pass

    return RedirectResponse(url="/payout/settings", status_code=303)


# ========= جديد: فحص الحالة وإرجاع JSON =========
@router.get("/api/stripe/connect/status")
def stripe_connect_status(request: Request, db: Session = Depends(get_db)):
    """
    تُستخدم من زر 'تحقّق من الحالة' في الواجهة.
    تجلب حساب Stripe من المصدر وتُرجع أعلام الحالة،
    وتحدّث عمود payouts_enabled في قاعدة البيانات إن وُجد.
    """
    sess = request.session.get("user")
    if not sess:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    ok, key = _api_key()
    if not ok:
        return JSONResponse({"error": "STRIPE_SECRET_KEY missing/invalid"}, status_code=500)

    stripe.api_key = key
    user = db.query(User).get(sess["id"])
    if not user:
        return JSONResponse({"error": "user_not_found"}, status_code=404)

    if not getattr(user, "stripe_account_id", None):
        return JSONResponse({
            "account_id": None,
            "payouts_enabled": False,
            "charges_enabled": False,
            "details_submitted": False
        })

    try:
        acct = stripe.Account.retrieve(user.stripe_account_id)
        payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
        charges_enabled = bool(getattr(acct, "charges_enabled", False))
        details_submitted = bool(getattr(acct, "details_submitted", False))

        # مزامنة سريعة مع الجدول
        if hasattr(user, "payouts_enabled") and user.payouts_enabled != payouts_enabled:
            user.payouts_enabled = payouts_enabled
            db.add(user)
            db.commit()

        return JSONResponse({
            "account_id": acct.id,
            "payouts_enabled": payouts_enabled,
            "charges_enabled": charges_enabled,
            "details_submitted": details_submitted
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)