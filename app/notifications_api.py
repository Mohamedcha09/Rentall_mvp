# app/notifications_api.py
from __future__ import annotations
from typing import Optional
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .database import get_db
from .models import User, Notification

router = APIRouter(tags=["notifications"])

# ============================================================
#                EMAIL SENDER (SMTP)
# ============================================================

SMTP_HOST = "mail.privateemail.com"
SMTP_PORT = 587
SMTP_USER = "no-reply@sevor.net"
SMTP_PASS = os.getenv("SMTP_PASSWORD")


def send_email_notification(to_email: str, subject: str, message: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject

        html = f"""
        <html>
        <body style="font-family:Arial;">
            <h3>{subject}</h3>
            <p>{message}</p>
            <br><p>Sevor — Rent Anything Worldwide</p>
        </body>
        </html>
        """

        msg.attach(MIMEText(message, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, to_email, msg.as_string())

        print("EMAIL SENT →", to_email)

    except Exception as e:
        print("EMAIL ERROR:", e)


def send_user_email(db: Session, user_id: int, subject: str, message: str):
    u = db.get(User, user_id)
    if not u or not u.email:
        print("❌ Cannot send email, missing email for user:", user_id)
        return

    send_email_notification(u.email, subject, message)


# ============================================================
#                CURRENT USER
# ============================================================
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None


def _json(data: dict) -> JSONResponse:
    return JSONResponse(
        data,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


# ============================================================
#               PUSH NOTIFICATIONS (DB + EMAIL)
# ============================================================
def push_notification(
    db: Session,
    user_id: int,
    title: str,
    body: str = "",
    url: Optional[str] = None,
    kind: str = "system",
) -> Notification:

    n = Notification(
        user_id=user_id,
        title=(title or "").strip()[:200],
        body=(body or "").strip()[:1000],
        link_url=url or "",
        kind=kind,
        is_read=False,
        created_at=datetime.utcnow(),
        opened_once=False,
    )
    db.add(n)
    db.commit()
    db.refresh(n)

    # Email fallback
    try:
        content = body or title
        if url:
            content += f"\n\nOpen: https://sevor.net{url}"

        send_user_email(db, user_id, title, content)

    except Exception as e:
        print("Email send error:", e)

    return n


# ============================================================
#               ADMIN + DM BROADCAST
# ============================================================

def notify_admins(db: Session, title: str, body: str = "", url: str = ""):
    admins = db.query(User).filter(User.role == "admin").all()
    for a in admins:
        push_notification(db, a.id, title, body, url, kind="admin")


def notify_dms(db: Session, title: str, body: str = "", url: str = ""):
    """
    إرسال إشعار فقط للـ Deposit Managers + Admin
    """
    dm_users = db.query(User).filter(
        (User.is_deposit_manager == True) | (User.role == "admin")
    ).all()

    for u in dm_users:
        push_notification(db, u.id, title, body, url, kind="deposit")


def notify_mods(db: Session, title: str, body: str = "", url: str = ""):
    rows = (
        db.query(User.id)
        .filter(or_(User.role == "admin", getattr(User, "is_mod") == True))
        .all()
    )
    ids = [r[0] for r in rows]
    for uid in ids:
        push_notification(db, uid, title, body, url, kind="support")


# ============================================================
# API ENDPOINTS BELOW
# ============================================================

@router.get("/api/unread_count")
def api_unread_count(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return _json({"count": 0})

    count = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.is_read == False)
        .count()
    )
    return _json({"count": int(count)})


@router.get("/api/notifications/poll")
def api_poll(
    request: Request,
    since: int = Query(0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)

    cutoff = datetime.utcfromtimestamp(since)

    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.created_at > cutoff)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )

    items = [
        {
            "id": r.id,
            "title": r.title,
            "body": r.body or "",
            "url": r.link_url or "",
            "ts": int(r.created_at.timestamp()),
            "kind": r.kind or "system",
            "is_read": bool(r.is_read),
        }
        for r in rows
    ]

    return _json({"now": int(datetime.utcnow().timestamp()), "items": items})


@router.post("/api/notifications/mark_all_read")
def mark_all_read(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)

    (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.is_read == False)
        .update({"is_read": True})
    )
    db.commit()

    return _json({"ok": True})


@router.post("/api/notifications/{notif_id}/read")
def mark_read(
    notif_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)

    n = db.get(Notification, notif_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404)

    n.is_read = True
    db.commit()

    return _json({"ok": True})


@router.get("/notifications/open/{notif_id}")
def open_notification(
    notif_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    n = db.get(Notification, notif_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404)

    if n.opened_once:
        return request.app.templates.TemplateResponse(
            "notification_used_once.html",
            {"request": request, "session_user": user},
        )

    n.opened_once = True
    n.opened_at = datetime.utcnow()
    n.is_read = True
    db.commit()

    item_id = request.query_params.get("item_id")

    if n.kind == "reject_edit" and item_id:
        return RedirectResponse(
            url=f"/owner/items/{item_id}/edit",
            status_code=303,
        )

    return RedirectResponse(url="/notifications", status_code=303)