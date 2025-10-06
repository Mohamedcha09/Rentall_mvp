# app/notifications.py
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Notification

router = APIRouter(tags=["notifications"])

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None

# ====== helper: إنشاء إشعار واحد ======
def push_notif(db: Session, user_id: int, title: str, body: str = "", *,
               kind: str = "info", link_url: str | None = None) -> None:
    if not user_id or not title:
        return
    n = Notification(user_id=user_id, title=title, body=body, kind=kind, link_url=link_url)
    db.add(n)
    # لا نعمل commit هنا دائماً — لكي يُندمج ضمن ترانزاكشن الراوتر
    # لكن في بعض الحالات قد نحتاج flush لضمان ID
    db.flush()

# ====== API: عدد غير المقروء ======
@router.get("/api/notifs/unread_count")
def unread_count(request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    if not user:
        return JSONResponse({"count": 0})
    cnt = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()
    return JSONResponse({"count": int(cnt)})

# ====== API: قائمة مبسطة لآخر الإشعارات ======
@router.get("/api/notifs/list")
def list_notifs(
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
                "kind": n.kind,
                "link": n.link_url or "",
                "is_read": bool(n.is_read),
                "created_at": n.created_at.isoformat()
            } for n in rows
        ]
    })

# ====== API: تعليم الكل كمقروء ======
@router.post("/api/notifs/mark_all_read")
def mark_all_read(request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).update({"is_read": True})
    db.commit()
    return JSONResponse({"ok": True})