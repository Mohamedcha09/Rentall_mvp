# app/admin.py
from datetime import datetime
import os

from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Document, MessageThread, Message
from .notifications_api import push_notification  # In-site notification
from .email_service import send_email             # Send email via SendGrid

router = APIRouter()

BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")

LOGO_URL  = f"{BASE_URL}/static/img/sevor-logo.png"
BRAND_URL = f"{BASE_URL}/static/images/base.png"

# ---------------------------
# Helpers
# ---------------------------
def require_admin(request: Request) -> bool:
    u = request.session.get("user")
    return bool(u and (u.get("role") or "").lower() == "admin")


def _open_or_create_admin_thread(db: Session, admin_id: int, user_id: int) -> MessageThread:
    """Open or create a message thread between the admin and the user."""
    thread = (
        db.query(MessageThread)
        .filter(
            ((MessageThread.user_a_id == admin_id) & (MessageThread.user_b_id == user_id)) |
            ((MessageThread.user_a_id == user_id) & (MessageThread.user_b_id == admin_id))
        )
        .order_by(MessageThread.created_at.desc())
        .first()
    )
    if not thread:
        thread = MessageThread(user_a_id=admin_id, user_b_id=user_id, item_id=None)
        db.add(thread)
        db.commit()
        db.refresh(thread)
    return thread


def _refresh_session_user_if_self(request: Request, user: User) -> None:
    """If the admin edited their own record, refresh values inside session so they appear immediately in the UI."""
    sess = request.session.get("user")
    if not sess or sess.get("id") != user.id:
        return
    sess["role"] = user.role
    sess["status"] = user.status
    sess["is_verified"] = bool(user.is_verified)
    # Badge flags
    for k in [
        "badge_admin", "badge_new_yellow", "badge_pro_green", "badge_pro_gold",
        "badge_purple_trust", "badge_renter_green", "badge_orange_stars",
    ]:
        if hasattr(user, k):
            sess[k] = getattr(user, k)
    # Special permissions
    if hasattr(user, "is_deposit_manager"):
        sess["is_deposit_manager"] = bool(getattr(user, "is_deposit_manager", False))
    if hasattr(user, "is_mod"):
        sess["is_mod"] = bool(getattr(user, "is_mod", False))
    if hasattr(user, "is_support"):
        sess["is_support"] = bool(getattr(user, "is_support", False))
    request.session["user"] = sess


# ---------------------------
# Admin dashboard
# ---------------------------
@router.get("/admin")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    pending_users = (
        db.query(User)
        .filter(User.status == "pending")
        .order_by(User.created_at.desc())
        .all()
    )
    all_users = db.query(User).order_by(User.created_at.desc()).all()

    return request.app.templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "title": "Admin Dashboard",
            "pending_users": pending_users,
            "all_users": all_users,
            "session_user": request.session.get("user"),
        },
    )


# ---------------------------
# Registration decisions
# ---------------------------
@router.post("/admin/users/{user_id}/approve")
def approve_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Admin approval: enable booking by setting status to approved,
    and send an email indicating the state.
    """
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    user.status = "approved"

    for d in (user.documents or []):
        d.review_status = "approved"
        d.reviewed_at = datetime.utcnow()

    db.commit()
    _refresh_session_user_if_self(request, user)

    # Send email based on email-verification state
    try:
        home_url = f"{BASE_URL}/"
        logo = f"{BASE_URL}/static/images/ok.png"
        brand = f"{BASE_URL}/static/images/base.png"

        if bool(getattr(user, "is_verified", False)):
            subject = "Your account is 100% activated — You can book now 🎉"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>100% Activation</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,'Segoe UI',sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0">Your account is 100% activated — You can book now</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b0f1a;padding:24px 12px">
    <tr><td align="center">
      <table role="presentation" width="640" cellspacing="0" cellpadding="0"
             style="width:100%;max-width:640px;background:#0f172a;border:1px solid #1f2937;border-radius:16px;overflow:hidden">
        <tr>
          <td style="padding:20px 24px;background:linear-gradient(90deg,#111827,#0b1220)">
            <table width="100%"><tr>
              <td align="right"><img src="{brand}" alt="" style="height:22px;opacity:.95"></td>
              <td align="left"><img src="{logo}" alt="" style="height:36px;border-radius:8px"></td>
            </tr></table>
          </td>
        </tr>
        <tr><td style="padding:28px 26px">
          <h2 style="margin:0 0 12px;font-size:22px;color:#fff;">Hi {user.first_name or ''} 👋</h2>
          <p style="margin:0 0 12px;line-height:1.9;color:#cbd5e1">
            Admin approval completed and your account is now <b style="color:#fff">100% activated</b>.
          </p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:26px auto">
            <tr><td bgcolor="#16a34a" style="border-radius:10px;">
              <a href="{home_url}" target="_blank"
                 style="font-family:Tahoma,Arial,sans-serif;font-size:16px;line-height:16px;text-decoration:none;
                        padding:14px 22px;display:inline-block;color:#ffffff;border-radius:10px;font-weight:700">
                Start now
              </a>
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:18px 24px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          If you didn’t request this action, please ignore this message.
        </td></tr>
      </table>
      <div style="color:#64748b;font-size:11px;margin-top:12px">&copy; {year} RentAll</div>
    </td></tr>
  </table>
</body></html>"""
            text = f"Hi {user.first_name}\n\nYour account is 100% activated and you can now book.\n{home_url}"
        else:
            verify_page = f"{BASE_URL}/verify-email?email={user.email}"
            subject = "Admin approved — Verify your email to reach 100%"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Complete Email Verification</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,'Segoe UI',sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0">Approval complete — Finish email verification to complete your account</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b0f1a;padding:24px 12px">
    <tr><td align="center">
      <table role="presentation" width="640" cellspacing="0" cellpadding="0"
             style="width:100%;max-width:640px;background:#0f172a;border:1px solid #1f2937;border-radius:16px;overflow:hidden">
        <tr>
          <td style="padding:20px 24px;background:linear-gradient(90deg,#111827,#0b1220)">
            <table width="100%"><tr>
              <td align="right"><img src="{brand}" alt="" style="height:22px;opacity:.95"></td>
              <td align="left"><img src="{logo}" alt="" style="height:36px;border-radius:8px"></td>
            </tr></table>
          </td>
        </tr>
        <tr><td style="padding:28px 26px">
          <h2 style="margin:0 0 12px;font-size:22px;color:#fff;">Hi {user.first_name or ''} 👋</h2>
          <p style="margin:0 0 12px;line-height:1.9;color:#cbd5e1">
            Admin has approved your account. One step left to reach 100%: <b style="color:#fff">verify your email</b>.
          </p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:26px auto">
            <tr><td bgcolor="#2563eb" style="border-radius:10px;">
              <a href="{verify_page}" target="_blank"
                 style="font-family:Tahoma,Arial,sans-serif;font-size:16px;line-height:16px;text-decoration:none;
                        padding:14px 22px;display:inline-block;color:#ffffff;border-radius:10px;font-weight:700">
                Activation instructions
              </a>
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:18px 24px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          If you didn’t request this action, please ignore this message.
        </td></tr>
      </table>
      <div style="color:#64748b;font-size:11px;margin-top:12px">&copy; {year} RentAll</div>
    </td></tr>
  </table>
</body></html>"""
            text = f"Hi {user.first_name}\n\nAdmin has approved your account. To reach 100%, verify your email from the verification message.\n{verify_page}"

        send_email(user.email, subject, html, text_body=text)
    except Exception:
        pass

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/reject")
def reject_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    user.status = "rejected"
    for d in (user.documents or []):
        d.review_status = "rejected"
        d.reviewed_at = datetime.utcnow()
    db.commit()
    _refresh_session_user_if_self(request, user)

    # Rejection email (optional)
    try:
        subject = "Your account was not accepted at this time"
        html = f"""
        <div style="font-family:Tahoma,Arial,sans-serif;direction:ltr;text-align:left;line-height:1.8">
          <p>Sorry, your account was not accepted at this time. You can re-upload clear photos of your ID and your selfie, then request another review.</p>
          <p><a href="{BASE_URL}/activate">Complete activation</a></p>
        </div>
        """
        send_email(user.email, subject, html, text_body="Your account was not accepted at this time.")
    except Exception:
        pass

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# Verification
# ---------------------------
@router.post("/admin/users/{user_id}/verify")
def verify_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    user.is_verified = True
    if hasattr(user, "verified_at"):
        user.verified_at = datetime.utcnow()
    if hasattr(user, "verified_by_id") and admin:
        user.verified_by_id = admin.get("id")
    db.commit()
    _refresh_session_user_if_self(request, user)

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/unverify")
def unverify_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    user.is_verified = False
    if hasattr(user, "verified_at"):
        user.verified_at = None
    if hasattr(user, "verified_by_id"):
        user.verified_by_id = None
    db.commit()
    _refresh_session_user_if_self(request, user)

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# Review individual documents
# ---------------------------
@router.post("/admin/documents/{doc_id}/approve")
def approve_document(doc_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    doc = db.query(Document).get(doc_id)
    if doc:
        doc.review_status = "approved"
        doc.reviewed_at = datetime.utcnow()
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/documents/{doc_id}/reject")
def reject_document(doc_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    doc = db.query(Document).get(doc_id)
    if doc:
        doc.review_status = "rejected"
        doc.reviewed_at = datetime.utcnow()
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# Message the user + request a fix
# ---------------------------
@router.post("/admin/users/{user_id}/message")
def admin_message_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    if not admin:
        return RedirectResponse(url="/login", status_code=303)

    thread = _open_or_create_admin_thread(db, admin["id"], user_id)

    first_msg = db.query(Message).filter(Message.thread_id == thread.id).first()
    if not first_msg:
        db.add(Message(thread_id=thread.id, sender_id=admin["id"], body="Hello! Please complete/fix your verification data."))
        db.commit()

    return RedirectResponse(url=f"/messages/{thread.id}", status_code=303)


@router.post("/admin/users/{user_id}/request_fix")
def admin_request_fix(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    reason: str = Form("We need a clearer photo or a valid document."),
):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    if not admin:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    for d in (user.documents or []):
        d.review_status = "needs_fix"
        d.reviewed_at = datetime.utcnow()
        if d.review_note:
            d.review_note = f"{d.review_note.strip()}\n- {reason.strip()}"
        else:
            d.review_note = reason.strip()

    db.commit()

    thread = _open_or_create_admin_thread(db, admin["id"], user_id)
    fix_link = "/profile/docs"
    body = f"Hello {user.first_name},\nThere are notes on your verification documents:\n- {reason}\nPlease fix them here: {fix_link}"
    db.add(Message(thread_id=thread.id, sender_id=admin["id"], body=body))
    db.commit()

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# Badges management
# ---------------------------
@router.post("/users/{user_id}/badges")
def set_badges(
    user_id: int,
    badge_purple_trust: str | None = Form(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if not u:
        return RedirectResponse(url="/admin", status_code=303)

    u.badge_purple_trust = bool(badge_purple_trust)
    u.is_verified = u.badge_purple_trust
    db.add(u)
    db.commit()
    db.refresh(u)
    _refresh_session_user_if_self(request, u)
    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# Deposit Manager (DM) permission management
# ---------------------------
@router.post("/admin/users/{user_id}/deposit_manager/enable")
def enable_deposit_manager(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_deposit_manager"):
        u.is_deposit_manager = True
        db.commit()
        _refresh_session_user_if_self(request, u)

        # In-site notification
        push_notification(
            db, u.id,
            "You’ve been granted the Deposit Manager role 🎉",
            "You can now review deposits and make decisions.",
            "/dm/deposits",
            "role"
        )

        # Email: role granted
        try:
            subject = "🎉 Deposit Manager role granted — Welcome to the review panel"
            home = f"{BASE_URL}/dm/deposits"
            logo = f"{BASE_URL}/static/images/ok.png"
            brand = f"{BASE_URL}/static/images/base.png"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deposit Manager role granted</title></head>
<body style="margin:0;background:#0b0f1a;font-family:Tahoma,Arial,sans-serif;color:#e5e7eb">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;background:#0b0f1a">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:640px;border-radius:20px;overflow:hidden;
                    background:linear-gradient(135deg,rgba(17,24,39,.85),rgba(2,6,23,.85));
                    border:1px solid rgba(148,163,184,.25);backdrop-filter:blur(8px)">
        <tr>
          <td style="padding:18px 22px;background:linear-gradient(90deg,#111827,#0b1220)">
            <table width="100%"><tr>
              <td align="right"><img src="{brand}" style="height:22px;opacity:.95" alt=""></td>
              <td align="left"><img src="{logo}" style="height:36px;border-radius:10px" alt=""></td>
            </tr></table>
          </td>
        </tr>
        <tr><td style="padding:28px 26px">
          <h2 style="margin:0 0 10px;color:#fff">Hello {u.first_name or 'friend'} 🎉</h2>
          <p style="margin:0 0 12px;line-height:1.9;color:#cbd5e1">
            You’ve been granted the <b style="color:#fff">Deposit Manager</b> role. You can now access the cases panel,
            review evidence, and make final decisions.
          </p>
          <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:22px auto">
            <tr><td bgcolor="#16a34a" style="border-radius:12px">
              <a href="{home}" target="_blank"
                 style="display:inline-block;padding:14px 22px;color:#fff;text-decoration:none;font-weight:700;border-radius:12px">
                 Open deposit panel
              </a>
            </td></tr>
          </table>
          <p style="margin:8px 0 0;color:#94a3b8;font-size:13px">Tip: enable notifications to receive case updates instantly.</p>
        </td></tr>
        <tr><td style="padding:16px 22px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          &copy; {year} RentAll
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
            text = f"You’ve been granted the Deposit Manager role. Admin panel: {home}"
            send_email(u.email, subject, html, text_body=text)
        except Exception:
            pass

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/deposit_manager/disable")
def disable_deposit_manager(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_deposit_manager"):
        u.is_deposit_manager = False
        db.commit()
        _refresh_session_user_if_self(request, u)

        push_notification(
            db, u.id,
            "Deposit Manager role removed",
            "You no longer have permission to manage deposits.",
            "/",
            "role"
        )

        # Email: role removed
        try:
            subject = "Deposit Manager role removed"
            home = f"{BASE_URL}/"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Permission removed</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;background:#0b0f1a">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:640px;border-radius:18px;overflow:hidden;background:#0f172a;border:1px solid #1f2937">
        <tr><td style="padding:26px 24px">
          <h3 style="margin:0 0 8px;color:#fff">Deposit Manager role removed</h3>
          <p style="margin:0;line-height:1.9;color:#cbd5e1">
            The permission to manage deposits has been removed from your account. You can still use the rest of the site features as usual.
          </p>
          <p style="margin:18px 0 0"><a href="{home}" style="color:#60a5fa;text-decoration:none">Back to homepage</a></p>
        </td></tr>
        <tr><td style="padding:14px 22px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          &copy; {year} RentAll
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
            text = f"The Deposit Manager role has been removed from your account. For more details: {home}"
            send_email(u.email, subject, html, text_body=text)
        except Exception:
            pass

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# MOD permission (content moderator) management
# ---------------------------
@router.post("/admin/users/{user_id}/mod/enable")
def enable_mod(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Grant the Content Moderator (MOD) permission to the user."""
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_mod"):
        u.is_mod = True
        db.commit()
        _refresh_session_user_if_self(request, u)

        try:
            push_notification(
                db, u.id,
                "🎉 You’ve been granted the Content Moderator (MOD) role",
                "You can now review reports and take appropriate actions.",
                "/mod/reports",
                "role"
            )
        except Exception:
            pass

        try:
            subject = "🎉 MOD permission granted"
            home = f"{BASE_URL}/mod/reports"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MOD permission granted</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;background:#0b0f1a">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:640px;border-radius:18px;overflow:hidden;background:#0f172a;border:1px solid #1f2937">
        <tr><td style="padding:26px 24px">
          <h3 style="margin:0 0 8px;color:#fff">Content Moderator permission granted</h3>
          <p style="margin:0;line-height:1.9;color:#cbd5e1">
            You can now access the reports dashboard and make delete/reject/warn decisions.
          </p>
          <p style="margin:18px 0 0"><a href="{home}" style="color:#60a5fa;text-decoration:none">Open reports dashboard</a></p>
        </td></tr>
        <tr><td style="padding:14px 22px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          &copy; {year} RentAll
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
            text = f"You’ve been granted the Content Moderator (MOD) permission. Start here: {home}"
            send_email(u.email, subject, html, text_body=text)
        except Exception:
            pass

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/mod/disable")
def disable_mod(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Revoke the Content Moderator (MOD) permission from the user."""
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_mod"):
        u.is_mod = False
        db.commit()
        _refresh_session_user_if_self(request, u)

        try:
            push_notification(
                db, u.id,
                "Content Moderator permission removed",
                "You no longer have permission to review reports.",
                "/",
                "role"
            )
        except Exception:
            pass

        try:
            subject = "Content Moderator (MOD) permission removed"
            home = f"{BASE_URL}/"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MOD permission removed</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;background:#0b0f1a">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:640px;border-radius:18px;overflow:hidden;background:#0f172a;border:1px solid #1f2937">
        <tr><td style="padding:26px 24px">
          <h3 style="margin:0 0 8px;color:#fff">Content Moderator permission removed</h3>
          <p style="margin:0;line-height:1.9;color:#cbd5e1">
            The permission to review reports has been revoked from your account. You can still use the rest of the site features as usual.
          </p>
          <p style="margin:18px 0 0"><a href="{home}" style="color:#60a5fa;text-decoration:none">Back to homepage</a></p>
        </td></tr>
        <tr><td style="padding:14px 22px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          &copy; {year} RentAll
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
            text = f"The Content Moderator permission has been removed from your account. For more details: {home}"
            send_email(u.email, subject, html, text_body=text)
        except Exception:
            pass

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# CS permission (customer support) management
# ---------------------------
@router.post("/admin/users/{user_id}/cs/enable")
def enable_support(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Grant Customer Support (CS) permission."""
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_support"):
        u.is_support = True
        db.commit()
        _refresh_session_user_if_self(request, u)

        try:
            push_notification(
                db, u.id,
                "🎧 Customer Support (CS) permission granted",
                "You can now access the support ticket inbox.",
                "/cs/inbox",
                "role"
            )
        except Exception:
            pass

        try:
            subject = "🎧 Customer Support (CS) permission granted"
            home = f"{BASE_URL}/cs/inbox"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CS permission granted</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;background:#0b0f1a">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:640px;border-radius:18px;overflow:hidden;background:#0f172a;border:1px solid #1f2937">
        <tr><td style="padding:26px 24px">
          <h3 style="margin:0 0 8px;color:#fff">Customer Support permission granted</h3>
          <p style="margin:0;line-height:1.9;color:#cbd5e1">
            You can now assign/respond to tickets in the support panel.
          </p>
          <p style="margin:18px 0 0"><a href="{home}" style="color:#60a5fa;text-decoration:none">Open inbox</a></p>
        </td></tr>
        <tr><td style="padding:14px 22px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          &copy; {year} RentAll
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
            text = f"Customer Support (CS) permission granted. Support panel: {home}"
            send_email(u.email, subject, html, text_body=text)
        except Exception:
            pass

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/cs/disable")
def disable_support(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Revoke Customer Support (CS) permission."""
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_support"):
        u.is_support = False
        db.commit()
        _refresh_session_user_if_self(request, u)

        try:
            push_notification(
                db, u.id,
                "Customer Support permission removed",
                "You no longer have permission to manage support tickets.",
                "/",
                "role"
            )
        except Exception:
            pass

        try:
            subject = "Customer Support (CS) permission removed"
            home = f"{BASE_URL}/"
            year = datetime.utcnow().year
            html = f"""<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CS permission removed</title></head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;font-family:Tahoma,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;background:#0b0f1a">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:640px;border-radius:18px;overflow:hidden;background:#0f172a;border:1px solid #1f2937">
        <tr><td style="padding:26px 24px">
          <h3 style="margin:0 0 8px;color:#fff">Customer Support permission removed</h3>
          <p style="margin:0;line-height:1.9;color:#cbd5e1">
            The permission to manage support tickets has been revoked from your account.
          </p>
          <p style="margin:18px 0 0"><a href="{home}" style="color:#60a5fa;text-decoration:none">Back to homepage</a></p>
        </td></tr>
        <tr><td style="padding:14px 22px;background:#0b1220;color:#94a3b8;font-size:12px;text-align:center">
          &copy; {year} RentAll
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
            text = f"The Customer Support (CS) permission has been removed from your account. More details: {home}"
            send_email(u.email, subject, html, text_body=text)
        except Exception:
            pass

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# Admin Broadcast Email (Send to all users)
# ---------------------------
@router.get("/admin/broadcast")
def broadcast_page(request: Request):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    return request.app.templates.TemplateResponse(
        "admin_broadcast.html",
        {
            "request": request,
            "title": "Broadcast Email",
            "session_user": request.session.get("user"),  # ← مهم جداً
        },
    )


@router.post("/admin/broadcast")
def broadcast_send(
    request: Request,
    subject: str = Form(...),
    message: str = Form(...),
    audience: str = Form("all"),
    db: Session = Depends(get_db),
):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    # 1) اختَر الجمهور
    query = db.query(User.email).filter(User.email.isnot(None))
    if audience == "verified":
        query = query.filter(User.is_verified == True)
    elif audience == "unverified":
        query = query.filter((User.is_verified == False) | (User.is_verified.is_(None)))

    emails = [row.email for row in query.all()]

    # لو ما في ولا إيميل
    if not emails:
        return request.app.templates.TemplateResponse(
            "admin_broadcast.html",
            {
                "request": request,
                "title": "Broadcast Email",
                "session_user": request.session.get("user"),
                "error": "No recipients found for this audience.",
            },
            status_code=400,
        )

    # 2) حضّر النصوص
    safe_subject = (subject or "").strip() or "📢 Announcement from Sevor"
    plain_text = (message or "").strip()
    msg_html = (message or "").replace("\n", "<br>")

    year = datetime.utcnow().year
    home_url = f"{BASE_URL}/"
    logo = LOGO_URL
    brand = BRAND_URL

    # 3) HTML ديزاين بسيط + لوغو من فوق
    html_body = f"""<!doctype html>
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{safe_subject}</title>
</head>
<body style="margin:0;background:#0b0f1a;color:#e5e7eb;
             font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="padding:24px 12px;background:#0b0f1a;">
    <tr>
      <td align="center">

        <table role="presentation" width="640" cellpadding="0" cellspacing="0"
               style="width:100%;max-width:640px;border-radius:20px;overflow:hidden;
                      background:#0f172a;border:1px solid #1f2937;">

          <!-- Header مع اللوغو -->
          <tr>
            <td style="padding:18px 22px;
                       background:linear-gradient(90deg,#111827,#0b1220);">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="left">
                    <img src="{logo}" alt="Sevor logo"
                         style="height:32px;border-radius:8px;display:block;" />
                  </td>
                  <td align="right"
                      style="font-size:13px;color:#9ca3af;">
                    Announcement from <span style="color:#e5e7eb;font-weight:600;">Sevor</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- محتوى الرسالة -->
          <tr>
            <td style="padding:26px 24px;">
              <h1 style="margin:0 0 12px;font-size:22px;color:#ffffff;
                         letter-spacing:0.02em;">
                {safe_subject}
              </h1>

              <div style="margin:8px 0 18px;height:1px;background:#1f2937;"></div>

              <div style="font-size:15px;line-height:1.8;color:#e5e7eb;">
                {msg_html}
              </div>

              <p style="margin:24px 0 0;font-size:13px;color:#9ca3af;">
                You are receiving this email because you have an active Sevor account.
                If you no longer want to receive announcements, reply <b>STOP</b>.
              </p>

              <p style="margin:20px 0 0;font-size:13px;">
                <a href="{home_url}"
                   style="display:inline-block;padding:10px 18px;
                          border-radius:999px;background:#6366f1;
                          color:#ffffff;text-decoration:none;font-weight:600;">
                  Open Sevor
                </a>
              </p>
            </td>
          </tr>

          <!-- Footer صغير -->
          <tr>
            <td style="padding:14px 22px;background:#020617;
                       font-size:11px;color:#6b7280;text-align:center;">
              &copy; {year} Sevor. All rights reserved.
            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>
</body>
</html>"""

    # 4) إرسال الإيميل عبر SendGrid
    from .email_service import send_email
    ok = send_email(
        to=emails,
        subject=safe_subject,
        html_body=html_body,
        text_body=plain_text or safe_subject,
    )
    print("Broadcast send status:", ok, "to", len(emails), "users")

    # 5) صفحة النجاح
    return request.app.templates.TemplateResponse(
        "admin_broadcast_success.html",
        {
            "request": request,
            "title": "Broadcast Sent",
            "sent_to": len(emails),
            "session_user": request.session.get("user"),
        },
    )
