# app/payout_connect.py
import os
# import smtplib
# from email.mime.text import MIMEText

import stripe
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .notifications_api import push_notification, notify_admins  # ⬅ إشعارات داخل الموقع

# ===== [جديد] نستخدم SendGrid مباشرة عبر هذه الخدمة =====
from .email_service import send_email as _sg_send_email  # (to, subject, html_body, text_body=None, ...)

router = APIRouter()

# =========================
# Email helper (simple SMTP) — تم إلغاؤه لصالح SendGrid (أبقيته كتعليقات)
# =========================
# def _send_email(to_email: str, subject: str, body: str) -> bool:
#     try:
#         host = os.getenv("EMAIL_HOST", "")
#         port = int(os.getenv("EMAIL_PORT", "587"))
#         user = os.getenv("EMAIL_USER", "")
#         pwd  = os.getenv("EMAIL_PASS", "")
#         use_tls = str(os.getenv("EMAIL_USE_TLS", "True")).lower() in ("1", "true", "yes")
#         if not (host and port and user and pwd and to_email):
#             return False
#         msg = MIMEText(body, _charset="utf-8")
#         msg["Subject"] = subject
#         msg["From"] = user
#         msg["To"] = to_email
#         smtp = smtplib.SMTP(host, port, timeout=20)
#         try:
#             if use_tls:
#                 smtp.starttls()
#             smtp.login(user, pwd)
#             smtp.sendmail(user, [to_email], msg.as_string())
#         finally:
#             try:
#                 smtp.quit()
#             except Exception:
#                 pass
#         return True
#     except Exception:
#         return False

# ===== قاعدة الروابط =====
BASE_URL = (os.getenv("SITE_URL") or os.getenv("CONNECT_REDIRECT_BASE") or "http://localhost:8000").rstrip("/")

# ===== [قديم] الاعتماد على app/emailer — تركناه كتعليق
# try:
#     from .emailer import send_email as _templated_send_email
# except Exception:
#     _templated_send_email = None

def _strip_html(html: str) -> str:
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
    ⬅ الآن نستخدم SendGrid فقط عبر app/email_service.send_email
    """
    try:
        return bool(_sg_send_email(
            to=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body or _strip_html(html_body),
        ))
    except Exception:
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
    """
    ينشئ حساب Express إذا غير موجود ويحفظه في DB، ويعيد acct_id
    """
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

# ===== [جديد] دالة ترسل إيميل “تم التفعيل بالكامل” فقط عند true/true/true =====
def _maybe_send_full_ready_email(request: Request, db: Session, user: User, acct: stripe.Account) -> None:
    try:
        # لا نرسل إلا مرة واحدة لكل جلسة
        if (request.session or {}).get("stripe_activation_emailed"):
            return

        payouts_enabled   = bool(getattr(acct, "payouts_enabled", False))
        charges_enabled   = bool(getattr(acct, "charges_enabled", False))
        details_submitted = bool(getattr(acct, "details_submitted", False))

        all_true = payouts_enabled and charges_enabled and details_submitted
        if not all_true:
            return

        # نص/HTML
        verify_url = f"{BASE_URL}/payout/settings"
        subject = "🎉 تم تفعيل حساب Stripe Connect بالكامل"
        html = f"""
        <div style="direction:rtl;text-align:right;font-family:Tahoma,Arial,'Segoe UI',sans-serif;line-height:1.9">
          <h2 style="margin:0 0 10px">تهانينا 🎉</h2>
          <p>تم تفعيل حسابك في <b>Stripe Connect</b> بالكامل:</p>
          <ul style="margin:0 0 14px">
            <li>payouts_enabled: <b>true</b></li>
            <li>charges_enabled: <b>true</b></li>
            <li>details_submitted: <b>true</b></li>
          </ul>
          <p>يمكنك الآن استلام أرباحك. راجع الحالة من <a href="{verify_url}">صفحة الإعدادات</a>.</p>
        </div>
        """
        text = (
            "تهانينا 🎉\n"
            "تم تفعيل حسابك في Stripe Connect بالكامل:\n"
            "- payouts_enabled: true\n- charges_enabled: true\n- details_submitted: true\n\n"
            f"تفاصيل أكثر: {verify_url}\n"
        )

        if user.email:
            ok = send_email(user.email, subject, html, text_body=text)
            # لو فشل الإرسال لا نكسر شيء، فقط ندوّن ونعلم الأدمن تشخيصيًا
            if not ok:
                notify_admins(db, "SendGrid: فشل إرسال بريد تفعيل Stripe", f"user_id={user.id}", "/admin")
            else:
                # منع التكرار في نفس الجلسة
                request.session["stripe_activation_emailed"] = True
    except Exception:
        # صمتًا
        pass

# =========================
# صفحة الإعدادات
# =========================
@router.get("/payout/settings", response_class=HTMLResponse)
def payout_settings(request: Request):
    t = request.app.templates
    return t.TemplateResponse("payout_settings.html", {"request": request, "session_user": request.session.get("user")})

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
@router.api_route("/payout/connect/start", methods=["GET","POST"])
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
        # (24) فشل ربط الحساب — إشعار بريد + إشعار داخل الموقع + إشعار للأدمن
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
            "/admin"
        )
        # بريد SendGrid (HTML + نص)
        try:
            send_email(
                user.email,
                "🪪 فشل ربط Stripe",
                (
                    f"<p>مرحبًا {user.first_name or ''},</p>"
                    f"<p>تعذّر بدء ربط حسابك على Stripe Connect.</p>"
                    f"<p>السبب (إن وُجد): {reason}</p>"
                    f'<p>حاول مجددًا من خلال <a href="{BASE_URL}/payout/settings">صفحة الإعدادات</a> '
                    f'أو تواصل مع الدعم.</p>'
                ),
                (
                    f"مرحبًا {user.first_name or ''},\n\n"
                    "تعذّر بدء ربط حسابك على Stripe Connect.\n"
                    f"السبب (إن وُجد): {reason}\n\n"
                    f"جرّب من جديد عبر صفحة الإعدادات: {BASE_URL}/payout/settings، أو تواصل مع الدعم."
                )
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
    يعود المستخدم من Stripe هنا (refresh/return).
    نزامن الحالة، ثم إن أصبحت TRUE/TRUE/TRUE نرسل إيميل التفعيل بالكامل.
    """
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

            # sync flags المخزّنة (اختياري)
            try:
                if getattr(user, "stripe_account_id", None) != acct.id:
                    user.stripe_account_id = acct.id
            except Exception:
                pass
            if hasattr(user, "payouts_enabled"):
                user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user); db.commit()

            # أرسل الإيميل إذا أصبحت الحالة كاملة
            _maybe_send_full_ready_email(request, db, user, acct)

    except Exception as e:
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
            "/admin"
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
                    f"جرّب من جديد عبر صفحة الإعدادات: {BASE_URL}/payout/settings، أو تواصل مع الدعم."
                )
            )
        except Exception:
            pass

    return RedirectResponse(url="/payout/settings", status_code=303)

# =========================
# Status + Force Save
# =========================
@router.get("/api/stripe/connect/status")
def stripe_connect_status(
    request: Request,
    db: Session = Depends(get_db),
    autocreate: int = 0,
    send: int = Query(0, description="إن كانت =1 سيُرسل إيميل تفعيل عند اكتمال الشروط"),
):
    """
    endpoint JSON لقراءة حالة الحساب.
    لو `send=1` وكانّت الشروط TRUE/TRUE/TRUE سيُرسل إيميل التفعيل (مرة/جلسة).
    """
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

    # حفظ تلقائي (اختياري)
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

    # لو طلب send=1 جرّب إرسال بريد التفعيل
    if int(send or 0) == 1:
        _maybe_send_full_ready_email(request, db, user, acct)

    return JSONResponse({
        "connected": True,
        "account_id": acct.id,
        "charges_enabled": bool(acct.charges_enabled),
        "payouts_enabled": bool(acct.payouts_enabled),
        "details_submitted": bool(acct.details_submitted),
        "capabilities": getattr(acct, "capabilities", None),
        "requirements_due": acct.get("requirements", {}).get("currently_due", []),
        "emailed_this_session": bool((request.session or {}).get("stripe_activation_emailed")),
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
# Split Test (Destination charge) — كما هو
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

# === Onboard link as JSON (نفسه)
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