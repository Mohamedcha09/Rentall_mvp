# app/notifications_api.py
from __future__ import annotations
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .database import get_db
from .models import User, Notification

router = APIRouter(tags=["notifications"])


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
#                     PUSH NOTIFICATION
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
        opened_at=None,
    )

    db.add(n)
    db.commit()
    db.refresh(n)
    return n


# ============================================================
#                      BROADCAST
# ============================================================
def notify_admins(db: Session, title: str, body: str = "", url: str = "") -> None:
    admins = db.query(User).filter(User.role == "admin").all()
    for a in admins:
        push_notification(db, a.id, title, body, url, kind="admin")


# === MD broadcast helper ===========================================
# Notifies all Deposit Managers (MD) + Admins about a new ticket or task
def notify_mds(db, title: str, body: str, url: str = "/md/inbox", kind: str = "support") -> int:
    """
    Sends a notification to all users who have is_deposit_manager=True or role='admin'.
    Returns the number of recipients (best-effort).
    """
    sent = 0
    try:
        md_users = (
            db.query(User)
              .filter((User.is_deposit_manager == True) | (User.role == "admin"))
              .all()
        )
        for u in md_users:
            try:
                push_notification(db, u.id, title, body, url=url, kind=kind)
                sent += 1
            except Exception:
                pass
    except Exception:
        pass

    return sent

def notify_mods(db: Session, title: str, body: str = "", url: str = "") -> None:
    rows = (
        db.query(User.id)
        .filter(or_(User.role == "admin", getattr(User, "is_mod") == True))
        .distinct()
        .all()
    )
    ids = [r[0] if isinstance(r, tuple) else r.id for r in rows]
    for uid in ids:
        push_notification(db, uid, title, body, url, kind="support")


# ============================================================
#                      API: unread_count
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


# ============================================================
#                      API: POLLING
# ============================================================
@router.get("/api/notifications/poll")
def api_poll(
    request: Request,
    since: int = Query(0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)

    cutoff = datetime.utcfromtimestamp(since or 0)

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

    now = int(datetime.utcnow().timestamp())
    return _json({"now": now, "items": items})


# ============================================================
#                 API: mark all read
# ============================================================
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


# ============================================================
#                 API: mark a single read
# ============================================================
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


# ============================================================
#                 OPEN NOTIFICATION (ONE-TIME LINK)
# ============================================================
@router.get("/notifications/open/{notif_id}")
def open_notification(
    notif_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)

    n = db.get(Notification, notif_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Notification not found")

    # ========================================================
    #         ONLY FOR reject_edit → allow ONCE
    # ========================================================
    if n.kind == "reject_edit":

        
        if n.opened_once:
            return request.app.templates.TemplateResponse(
                "notification_used_once.html",
                {
                    "request": request
                    "session_user": user
                }
            )

        # أول فتح
        n.opened_once = True
        n.opened_at = datetime.utcnow()
        n.is_read = True
        db.commit()

        if n.link_url:
            return RedirectResponse(n.link_url, status_code=303)

        return RedirectResponse("/notifications", status_code=303)

    # ========================================================
    #           كل الإشعارات الأخرى تعمل طبيعي
    # ========================================================
    n.is_read = True
    db.commit()

    if n.link_url:
        return RedirectResponse(n.link_url, status_code=303)

    return RedirectResponse("/notifications", status_code=303)
