# app/notifications_api.py
from __future__ import annotations
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Notification

router = APIRouter(tags=["notifications"])

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None

def _json(data: dict) -> JSONResponse:
    return JSONResponse(data, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

# ✅ مطابق تمامًا للموديل: نستخدم link_url ولا نمرر meta/url
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
        link_url=url or "",          # <-- هذا هو اسم الحقل في الموديل
        kind=kind,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n

def notify_admins(db: Session, title: str, body: str = "", url: str = ""):
    admins = db.query(User).filter(User.role == "admin").all()
    for a in admins:
        push_notification(db, a.id, title, body, url, kind="admin")

@router.get("/api/unread_count")
def api_unread_count(db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    if not user:
        return _json({"count": 0})
    count = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()
    return _json({"count": int(count)})

@router.get("/api/notifications/poll")
def api_poll(
    request: Request,
    since: int = Query(0, description="Unix seconds of last poll"),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    cutoff = datetime.utcfromtimestamp(since or 0)
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.created_at > cutoff)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )
    items = [{
        "id": r.id,
        "title": r.title,
        "body": r.body or "",
        "url": r.link_url or "",
        "ts": int(r.created_at.timestamp()),
        "kind": r.kind or "system",
    } for r in rows]
    now = int(datetime.utcnow().timestamp())
    return _json({"now": now, "items": items})

@router.post("/api/notifications/{notif_id}/read")
def mark_read(notif_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    n = db.get(Notification, notif_id)
    if not n or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    n.is_read = True
    db.commit()
    return _json({"ok": True})

    @router.post("/api/notifications/mark_all_read")
def mark_all_read(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user)
):
    """Mark all notifications as read for the current user"""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"ok": True}