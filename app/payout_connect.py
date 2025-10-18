# app/payout_connect.py
import os
import stripe
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .notifications_api import push_notification, notify_admins  # إشعارات داخل الموقع

# ===== إرسال البريد عبر SendGrid (نفس خدمتك الحالية) =====
from .email_service import send_email as _sg_send_email  # (to, subject, html_body, text_body=None)

router = APIRouter()

# =========================
# ملاحظات مهمّة قبل التشغيل
# =========================
# تأكد من توفر المتغيّرات التالية في .env:
#   SENDGRID_API_KEY
#   FROM_EMAIL
#   FROM_NAME          (اختياري)
#   SITE_URL           (مثل: https://m3ak.onrender.com)
#   STRIPE_SECRET_KEY  (sk_test_... / sk_live_...)

# ===== قاعدة الروابط =====
BASE_URL = (os.getenv("SITE_URL") or os.getenv("CONNECT_REDIRECT_BASE") or "http://localhost:8000").rstrip("/")

# ===== بقايا SMTP القديمة (أبقيتها كتعليقات كما طلبت) =====
# import smtplib
# from email.mime.text import MIMEText
# def _send_email(...):  # تم الاستغناء عنها لصالح SendGrid
#     ...

def _strip_html(html: str) -> str:
    """تحويل HTML إلى نص بسيط عند الحاجة."""
    try:
        import re
        txt = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
        txt = re.sub(r"</p\s*>", "\n\n", txt, flags=re.I)
        txt = re.sub(r"<[^>]+>", "", txt)
        return txt.strip()
    except Exception:
        return html

def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """
    إرسال عبر SendGrid فقط (email_service.send_email).
    يرجع True عند النجاح، False عند الفشل — بدون رفع استثناءات.
    """
    if not to_email:
        print("[payout_connect] ⚠️ لا يوجد بريد للمستخدم — لن نرسل شيئًا.")
        return False
    try:
        ok = bool(
            _sg_send_email(
                to=to_email,
                subject=subject,
                html_body=html_body,
                text_body=text_body or _strip_html(html_body),
            )
        )
        print(f"[payout_connect] SendGrid result: {'OK' if ok else 'FAILED'} to={to_email} subj={subject}")
        return ok
    except Exception as e:
        print(f"[payout_connect] ⚠️ SendGrid exception: {e}")
        return False

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
    """ينشئ حساب Express إذا غير موجود ويحفظه في DB، ويعيد acct_id"""
    acct_id = getattr(user, "stripe_account_id", None)
    if not acct_id:
        acct = stripe.Account.create(
            type="express",
            country="CA",
            email=(user.email or None),
            capabilities={"card_payments": {"requested": True}, "transfers": {"requested": True}},
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
# صفحة الإعدادات
# =========================
@router.get("/payout/settings", response_class=HTMLResponse)
def payout_settings(request: Request):
    t = request.app.templates
    return t.TemplateResponse(
        "payout_settings.html",
        {"request": request, "session_user": request.session.get("user")},
    )

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

# يرجع الـ id مباشرة (ومفيد للتشخيص السريع)
@router.get("/api/stripe/connect/id")
def connect_account_id(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        raise HTTPException(401, "unauthenticated")
    user = db.query(User).get(sess["id"])
    if not user:
        raise HTTPException(404, "user_not_found")
    acct_id = getattr(user, "stripe_account_id", None) or request.session.get("connect_account_id")
    if not acct_id:
        return {"account_id": None}
    acct = stripe.Account.retrieve(acct_id)
    real_id = acct.id
    try:
        if getattr(user, "stripe_account_id", None) != real_id:
            user.stripe_account_id = real_id
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
        db.add(user); db.commit()
    except Exception:
        pass
    return {"account_id": real_id}

# =========================
# Start / Onboard / Refresh
# =========================
@router.api_route("/payout/connect/start", methods=["GET", "POST"])
def payout_connect_start(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    try:
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

    except Exception as e:
        # (24) فشل بدء الربط — إشعارات + إيميل
        reason = str(e)
        push_notification(
            db, user.id,
            "🪪 فشل ربط Stripe",
            "تعذّر بدء ربط حساب Stripe Connect. حاول مجددًا أو تواصل مع الدعم.",
            "/payout/settings",
            kind="system",
        )
        notify_admins(
            db,
            "Stripe Connect linking failed",
            f"user_id={user.id} — {reason[:180]}",
            "/admin",
        )
        try:
            send_email(
                user.email,
                "🪪 فشل ربط Stripe",
                (
                    f"<p>مرحبًا {user.first_name or ''},</p>"
                    f"<p>تعذّر بدء ربط حسابك على Stripe Connect.</p>"
                    f"<p>السبب (إن وُجد): {reason}</p>"
                    f'<p>أعد المحاولة من <a href="{BASE_URL}/payout/settings">صفحة الإعدادات</a> '
                    "أو تواصل مع الدعم.</p>"
                ),
                (
                    f"مرحبًا {user.first_name or ''},\n\n"
                    "تعذّر بدء ربط حسابك على Stripe Connect.\n"
                    f"السبب (إن وُجد): {reason}\n\n"
                    f"جرّب من جديد عبر صفحة الإعدادات: {BASE_URL}/payout/settings"
                ),
            )
        except Exception:
            pass
        return RedirectResponse(url="/payout/settings?err=1", status_code=303)

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
    """
    يعود المستخدم من Stripe هنا. نزامن الحالة،
    وإذا كانت payouts_enabled=True نرسل إشعار نجاح + إيميل SendGrid.
    - سابقًا: كنا نرسل فقط عند أول تحوّل (became_enabled).
    - الآن: سنرسل أيضًا إذا كان مفعّلًا مسبقًا لكن لم نرسل خلال الساعة الماضية
      (حماية من التكرار عبر session['stripe_connected_email_ts']).
    """
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/payout/settings", status_code=303)

    became_enabled = False
    try:
        if getattr(user, "stripe_account_id", None):
            acct = stripe.Account.retrieve(user.stripe_account_id)

            # sync flags
            try:
                if getattr(user, "stripe_account_id", None) != acct.id:
                    user.stripe_account_id = acct.id
            except Exception:
                pass

            pe = bool(getattr(acct, "payouts_enabled", False))
            before = bool(getattr(user, "payouts_enabled", False))
            if hasattr(user, "payouts_enabled"):
                user.payouts_enabled = pe
            db.add(user); db.commit()

            became_enabled = (pe and not before)

            should_email = False
            if pe:
                # 1) أول مرة → نرسل دائمًا
                if became_enabled:
                    should_email = True
                else:
                    # 2) مفعّل مسبقًا: نتحقق من آخر إرسال خلال ساعة
                    last_ts = request.session.get("stripe_connected_email_ts")
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    if not last_ts or (now_ts - int(last_ts)) > 3600:
                        should_email = True
                        request.session["stripe_connected_email_ts"] = now_ts

            if pe:
                # إشعار داخل الموقع دائمًا عند التفعيل
                push_notification(
                    db, user.id,
                    "🔗 تم ربط Stripe Connect بنجاح",
                    "أصبحت التحويلات مفعّلة على حسابك. يمكنك الآن استلام الأرباح.",
                    "/payout/settings",
                    kind="system",
                )
                notify_admins(
                    db,
                    "Stripe Connect linked",
                    f"user_id={user.id} — payouts_enabled=True",
                    "/admin",
                )

            if should_email:
                try:
                    send_email(
                        user.email,
                        "🔗 تم ربط Stripe Connect بنجاح",
                        (
                            f"<p>مرحبًا {user.first_name or ''},</p>"
                            "<p>تم ربط حساب Stripe Connect بنجاح وأصبحت التحويلات مفعّلة على حسابك.</p>"
                            f'<p>يمكنك مراجعة الحالة من <a href="{BASE_URL}/payout/settings">صفحة الإعدادات</a>.</p>'
                            "<p>شكرًا لاستخدامك منصّتنا.</p>"
                        ),
                        (
                            f"مرحبًا {user.first_name or ''},\n\n"
                            "تم ربط حساب Stripe Connect بنجاح وأصبحت التحويلات مفعّلة على حسابك.\n"
                            f"راجع صفحة الإعدادات: {BASE_URL}/payout/settings\n\n"
                            "شكرًا لاستخدامك منصّتنا."
                        ),
                    )
                except Exception:
                    pass

    except Exception as e:
        # فشل مزامنة/عودة
        reason = str(e)
        push_notification(
            db, user.id,
            "🪪 فشل مزامنة Stripe",
            "حدث خطأ أثناء مزامنة حالة Stripe. حاول مجددًا.",
            "/payout/settings",
            kind="system",
        )
        notify_admins(
            db, "Stripe Connect refresh failed",
            f"user_id={user.id} — {reason[:180]}",
            "/admin",
        )
        try:
            send_email(
                user.email,
                "🪪 فشل ربط/مزامنة Stripe",
                (
                    f"<p>مرحبًا {user.first_name or ''},</p>"
                    "<p>حدث خطأ أثناء مزامنة حساب Stripe Connect.</p>"
                    f"<p>السبب (إن وُجد): {reason}</p>"
                    f'<p>أعد المحاولة من <a href="{BASE_URL}/payout/settings">صفحة الإعدادات</a> '
                    "أو تواصل مع الدعم.</p>"
                ),
                (
                    f"مرحبًا {user.first_name or ''},\n\n"
                    "حدث خطأ أثناء مزامنة حساب Stripe Connect.\n"
                    f"السبب (إن وُجد): {reason}\n\n"
                    f"جرّب من جديد عبر صفحة الإعدادات: {BASE_URL}/payout/settings"
                ),
            )
        except Exception:
            pass

    qs = "?done=1" if became_enabled else ""
    return RedirectResponse(url=f"/payout/settings{qs}", status_code=303)

# =========================
# Status + Force Save (كما هي)
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
# Split Test (كما هو)
# =========================
@router.get("/split/test")
def split_test_checkout(
    request: Request,
    db: Session = Depends(get_db),
    amount: int = 2000,
    currency: str | None = None,
):
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
            "price_data": {"currency": cur, "product_data": {"name": "Test split order"}, "unit_amount": amount},
            "quantity": 1,
        }],
        payment_intent_data={
            "application_fee_amount": app_fee,
            "transfer_data": {"destination": acct_id},
        },
        metadata={"split_mode": "destination_charge", "acct": acct_id, "fee_pct": str(fee_pct)},
    )
    return RedirectResponse(session.url, status_code=303)

# === رابط onBoard كـ JSON (كما هو)
@router.get("/api/stripe/connect/onboard_link")
def connect_onboard_link(request: Request, db: Session = Depends(get_db)):
    _set_api_key_or_500()
    sess = request.session.get("user")
    if not sess:
        raise HTTPException(status_code=401, detail="unauthenticated")

    user = db.query(User).get(sess["id"])
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    acct_id = getattr(user, "stripe_account_id", None) or request.session.get("connect_account_id")
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
    return {"url": link.url}