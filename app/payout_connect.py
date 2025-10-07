# app/payout_connect.py
import os
import stripe
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter()

# -----------------------------
# Helpers
# -----------------------------
def get_base_url(request: Request) -> str:
    """
    يحدد الـ base URL لروابط العودة/الإنعاش:
    - يُفضِّل CONNECT_REDIRECT_BASE إن تم ضبطه (مثل https://m3ak.onrender.com)
    - وإلا يستخدم دومين الطلب ويجبر https (جيّد لـ Render)
    """
    env_base = (os.getenv("CONNECT_REDIRECT_BASE") or os.getenv("SITE_URL") or "").strip().rstrip("/")
    if env_base:
        return env_base
    # fallback: host الحالي لكن بصيغة https
    return f"https://{request.url.hostname}"

def require_session_user(request: Request) -> dict | None:
    return request.session.get("user")

def get_api_key_or_error() -> str:
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    if not (key.startswith("sk_test_") or key.startswith("sk_live_")):
        raise RuntimeError(
            "STRIPE_SECRET_KEY غير مضبوط أو غير صالح. استخدم مفتاح sk_test_ في وضع الاختبار أو sk_live_ في الوضع الحي."
        )
    return key

# دعم الفورم القديم: يجعلك تصل إلى نفس مسار البدء
@router.post("/payout/connect")
def connect_post_redirect():
    return RedirectResponse(url="/payout/connect/start", status_code=303)

# ---------------------------------
# 1) بدء/استكمال Stripe Onboarding
# ---------------------------------
@router.get("/payout/connect/start")
def connect_start(request: Request, db: Session = Depends(get_db)):
    """
    - يتطلب تسجيل دخول.
    - ينشئ حساب Stripe Connect Express للمستخدم إن لم يوجد.
    - ينشئ AccountLink ويرسلك لرحلة التوثيق في Stripe.
    """
    sess = require_session_user(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    try:
        stripe.api_key = get_api_key_or_error()
    except RuntimeError as e:
        return HTMLResponse(f"<h3>Stripe Key Error</h3><p>{e}</p>", status_code=500)

    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    try:
        # أنشئ حساب Stripe Express إن لم يكن موجودًا
        if not getattr(user, "stripe_account_id", None):
            acct = stripe.Account.create(type="express")
            user.stripe_account_id = acct.id
            db.add(user)
            db.commit()
        else:
            # تأكد أن الحساب موجود على Stripe
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
            "(sk_test_/pk_test_) أو تأكد من مفاتيح Live.</p>",
            status_code=401
        )
    except Exception as e:
        return HTMLResponse(f"<h3>Stripe Error</h3><pre>{str(e)}</pre>", status_code=500)

# -------------------------------------------------------
# 2) Refresh: تحديث حالة الحساب والرجوع لإعدادات التحويل
# -------------------------------------------------------
@router.get("/payout/connect/refresh")
def connect_refresh(request: Request, db: Session = Depends(get_db)):
    """
    - يُستدعى من Stripe أو يدويًا.
    - يجلب حساب Stripe ويحدّث user.payouts_enabled محليًا (إن كان العمود موجودًا).
    - ثم يعيد التوجيه إلى /payout/settings.
    """
    sess = require_session_user(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    try:
        stripe.api_key = get_api_key_or_error()
    except RuntimeError as e:
        return HTMLResponse(f"STRIPE_SECRET_KEY Error: {e}", status_code=500)

    user = db.query(User).get(sess["id"])
    if not user or not getattr(user, "stripe_account_id", None):
        return RedirectResponse(url="/payout/settings", status_code=303)

    try:
        acct = stripe.Account.retrieve(user.stripe_account_id)
        # لو عندك عمود payouts_enabled في جدول users — حدّثه
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user)
            db.commit()
    except Exception:
        # نتجاهل الخطأ الطفيف ونُعيد للواجهة
        pass

    return RedirectResponse(url="/payout/settings", status_code=303)

# ------------------------------------------------
# (اختياري) 3) حالة الحساب JSON للاستخدام من الواجهة
# ------------------------------------------------
@router.get("/payout/connect/status")
def connect_status_api(request: Request, db: Session = Depends(get_db)):
    """
    يُعيد JSON بحالة Stripe Connect للمستخدم (مفيد إن أردت جلبها بالـ fetch من القالب).
    """
    sess = require_session_user(request)
    if not sess:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    try:
        stripe.api_key = get_api_key_or_error()
    except RuntimeError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    user = db.query(User).get(sess["id"])
    if not user or not getattr(user, "stripe_account_id", None):
        return JSONResponse({"ok": True, "connected": False, "payouts_enabled": False}, status_code=200)

    try:
        acc = stripe.Account.retrieve(user.stripe_account_id)
        # مزامنة خفيفة محليًا
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(acc.get("payouts_enabled", False))
            db.add(user)
            db.commit()

        return JSONResponse({
            "ok": True,
            "connected": True,
            "payouts_enabled": bool(acc.get("payouts_enabled", False)),
            "charges_enabled": bool(acc.get("charges_enabled", False)),
            "details_submitted": bool(acc.get("details_submitted", False)),
            "capabilities": acc.get("capabilities", {}),
            "account_id": acc.get("id"),
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)