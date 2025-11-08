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
from .notifications_api import push_notification, notify_admins  # ⬅ In-site notifications

# ===== [New] Use SendGrid directly via this service =====
from .email_service import send_email as _sg_send_email  # (to, subject, html_body, text_body=None, ...)

router = APIRouter()

# =========================
# Email helper (simple SMTP) — removed in favor of SendGrid (kept as comments)
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

# ===== Base URLs =====
BASE_URL = (os.getenv("SITE_URL") or os.getenv("CONNECT_REDIRECT_BASE") or "http://localhost:8000").rstrip("/")

# ===== [Old] depending on app/emailer — left as comment
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
    ⬅ Now we use SendGrid only via app/email_service.send_email
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
    Creates an Express account if it does not exist, saves it to DB, and returns acct_id
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

# ===== [New] Send a “fully activated” email only when true/true/true =====
def _maybe_send_full_ready_email(request: Request, db: Session, user: User, acct: stripe.Account) -> None:
    try:
        # Send only once per session
        if (request.session or {}).get("stripe_activation_emailed"):
            return

        payouts_enabled   = bool(getattr(acct, "payouts_enabled", False))
        charges_enabled   = bool(getattr(acct, "charges_enabled", False))
        details_submitted = bool(getattr(acct, "details_submitted", False))

        all_true = payouts_enabled and charges_enabled and details_submitted
        if not all_true:
            return

        # Text/HTML
        verify_url = f"{BASE_URL}/payout/settings"
        subject = "🎉 Your Stripe Connect Account Is Fully Activated"
        html = f"""
        <div style="direction:rtl;text-align:right;font-family:Tahoma,Arial,'Segoe UI',sans-serif;line-height:1.9">
          <h2 style="margin:0 0 10px">Congratulations 🎉</h2>
          <p>Your <b>Stripe Connect</b> account is now fully activated:</p>
          <ul style="margin:0 0 14px">
            <li>payouts_enabled: <b>true</b></li>
            <li>charges_enabled: <b>true</b></li>
            <li>details_submitted: <b>true</b></li>
          </ul>
          <p>You can now receive your earnings. Check the status from the <a href="{verify_url}">settings page</a>.</p>
        </div>
        """
        text = (
            "Congratulations 🎉\n"
            "Your Stripe Connect account is fully activated:\n"
            "- payouts_enabled: true\n- charges_enabled: true\n- details_submitted: true\n\n"
            f"More details: {verify_url}\n"
        )

        if user.email:
            ok = send_email(user.email, subject, html, text_body=text)
            # If sending fails, do not break anything; just log and notify admin diagnostically
            if not ok:
                notify_admins(db, "SendGrid: Failed to send Stripe activation email", f"user_id={user.id}", "/admin")
            else:
                # Prevent duplication within the same session
                request.session["stripe_activation_emailed"] = True
    except Exception:
        # Silently ignore
        pass

# =========================
# Settings page
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

# Returns the id directly (useful for quick diagnostics)
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
        # (24) Account linking failed — email + in-site notification + admin notification
        reason = str(e)
        push_notification(
            db, user.id,
            "🪪 Stripe linking failed",
            "Could not start linking your Stripe Connect account. Please try again or contact support.",
            "/payout/settings",
            kind="system",
        )
        notify_admins(
            db,
            "Stripe Connect linking failed",
            f"user_id={user.id} — {reason[:180]}",
            "/admin"
        )
        # SendGrid email (HTML + text)
        try:
            send_email(
                user.email,
                "🪪 Stripe linking failed",
                (
                    f"<p>Hello {user.first_name or ''},</p>"
                    f"<p>We could not start linking your Stripe Connect account.</p>"
                    f"<p>Reason (if any): {reason}</p>"
                    f'<p>Please try again from the <a href="{BASE_URL}/payout/settings">settings page</a> '
                    f'or contact support.</p>'
                ),
                (
                    f"Hello {user.first_name or ''},\n\n"
                    "We could not start linking your Stripe Connect account.\n"
                    f"Reason (if any): {reason}\n\n"
                    f"Try again via the settings page: {BASE_URL}/payout/settings, or contact support."
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
    The user returns from Stripe here (refresh/return).
    We sync the status, then if it becomes TRUE/TRUE/TRUE we send the full activation email.
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

            # sync stored flags (optional)
            try:
                if getattr(user, "stripe_account_id", None) != acct.id:
                    user.stripe_account_id = acct.id
            except Exception:
                pass
            if hasattr(user, "payouts_enabled"):
                user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user); db.commit()

            # Send the email if the status is now complete
            _maybe_send_full_ready_email(request, db, user, acct)

    except Exception as e:
        reason = str(e)
        push_notification(
            db, user.id,
            "🪪 Stripe sync failed",
            "An error occurred while syncing Stripe status. Please try again.",
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
                "🪪 Stripe linking/sync failed",
                (
                    f"<p>Hello {user.first_name or ''},</p>"
                    "<p>An error occurred while syncing your Stripe Connect account.</p>"
                    f"<p>Reason (if any): {reason}</p>"
                    f'<p>Retry from the <a href="{BASE_URL}/payout/settings">settings page</a> '
                    "or contact support.</p>"
                ),
                (
                    f"Hello {user.first_name or ''},\n\n"
                    "An error occurred while syncing your Stripe Connect account.\n"
                    f"Reason (if any): {reason}\n\n"
                    f"Try again via the settings page: {BASE_URL}/payout/settings, or contact support."
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
    send: int = Query(0, description="If =1 will send activation email when conditions are met"),
):
    """
    JSON endpoint to read account status.
    If `send=1` and conditions are TRUE/TRUE/TRUE, it will send the activation email (once/session).
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

    # Auto-save (optional)
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

    # If send=1, try to send the activation email
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
# Split Test (Destination charge) — unchanged
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

# === Onboard link as JSON (same) 
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
