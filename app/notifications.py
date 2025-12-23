# app/notifications.py
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

# ========= helper: create a single notification =========
def push_notif(
    db: Session,
    user_id: int,
    title: str,
    body: str = "",
    *,
    kind: str = "info",
    link_url: str | None = None,
    do_commit: bool = True,           # <-- Important: commit by default
) -> Optional[Notification]:
    if not user_id or not (title or "").strip():
        return None
    n = Notification(
        user_id=user_id,
        title=(title or "").strip()[:200],
        body=(body or "").strip()[:1000],
        kind=kind or "info",
        link_url=link_url or "",
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    if do_commit:
        db.commit()
        try:
            db.refresh(n)
        except Exception:
            pass
    else:
        db.flush()
    return n

# ========= Old API (kept as-is) =========
@router.get("/api/notifs/unread_count")
def unread_count_legacy(
    request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)
):
    if not user:
        return JSONResponse({"count": 0})
    cnt = db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read == False
    ).count()
    return JSONResponse({"count": int(cnt)})

@router.get("/api/notifs/list")
def list_notifs_legacy(
    request: Request,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )
    return JSONResponse({
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body or "",
                "kind": n.kind or "info",
                "link": n.link_url or "",
                "is_read": bool(n.is_read),
                "created_at": n.created_at.isoformat()
            } for n in rows
        ]
    })

@router.post("/api/notifs/mark_all_read")
def mark_all_read_legacy(
    request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return JSONResponse({"ok": True})

# ========= ALIASES for the new frontend routes =========
# Even if the frontend hits /api/unread_count and /api/notifications/poll, they work from the same router

@router.get("/api/unread_count")
def api_unread_count(db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    if not user:
        return _json({"count": 0})
    count = db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read == False
    ).count()
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
def mark_read(
    notif_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    n = db.get(Notification, notif_id)
    if not n or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    n.is_read = True
    db.commit()
    return _json({"ok": True})


