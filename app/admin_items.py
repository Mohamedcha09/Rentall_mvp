# app/admin_items.py
from fastapi import APIRouter, Depends, Request, HTTPException, Form, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from .database import get_db
from .models import Item
from .notifications_api import push_notification

router = APIRouter(tags=["admin-items"], prefix="/admin/items")


# ==========================
#   CHECK ADMIN
# ==========================
def require_admin(request: Request):
    u = request.session.get("user")
    if not u or u.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return u

# ==========================
# FLASH MESSAGE
# ==========================
def flash(request: Request, message: str, category: str = "success"):
    request.session["flash_message"] = message
    request.session["flash_category"] = category


# ==========================
# 1) LIST PENDING ITEMS
# ==========================
@router.get("/pending")
def list_pending(request: Request, db: Session = Depends(get_db)):
    require_admin(request)

    items = (
        db.query(Item)
        .filter(Item.status == "pending")
        .order_by(Item.created_at.desc())
        .all()
    )

    return request.app.templates.TemplateResponse(
        "admin_items_pending.html",
        {
            "request": request,
            "items": items,
            "session_user": request.session.get("user"),
        }
    )

# ==========================
# 2) APPROVE ITEM
# ==========================
@router.post("/{item_id}/approve")
def approve_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)

    it = db.get(Item, item_id)    # ← FIXED
    if not it:
        raise HTTPException(404, "Item not found")

    it.status = "approved"
    it.reviewed_at = datetime.utcnow()
    it.admin_feedback = None
    db.commit()

    push_notification(
        db,
        user_id=it.owner_id,
        title="Your item was approved",
        body=f"Your listing '{it.title}' is now live.",
        url=f"/items/{it.id}"
    )

    return RedirectResponse(
        url="/admin/items/pending",
        status_code=status.HTTP_302_FOUND
    )


# ==========================
# 3) REJECT ITEM
# ==========================
@router.post("/{item_id}/reject")
def reject_item(item_id: int, request: Request, db: Session = Depends(get_db), feedback: str = Form("")):
    require_admin(request)

    it = db.get(Item, item_id)   # ← FIXED
    if not it:
        raise HTTPException(404, "Item not found")

    it.status = "rejected"
    it.admin_feedback = feedback
    it.reviewed_at = datetime.utcnow()
    db.commit()

    push_notification(
        db,
        user_id=it.owner_id,
        title="Your item was rejected",
        body=f"Your listing '{it.title}' requires changes.\nReason: {feedback}",
        url=f"/owner/items/{it.id}/edit"

    )

    return RedirectResponse(
        url="/admin/items/pending",
        status_code=status.HTTP_302_FOUND
    )


# ==========================
# 4) RESET TO PENDING
# ==========================
@router.post("/{item_id}/reset")
def reset_to_pending(item_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)

    it = db.get(Item, item_id)   # ← FIXED
    if not it:
        raise HTTPException(404, "Item not found")

    it.status = "pending"
    it.admin_feedback = None
    it.reviewed_at = None
    db.commit()

    return RedirectResponse(
        url="/admin/items/pending",
        status_code=status.HTTP_302_FOUND
    )


# ==========================
# 5) DELETE ITEM
# ==========================
@router.post("/{item_id}/delete")
def delete_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)

    it = db.get(Item, item_id)   # ← FIXED
    if not it:
        raise HTTPException(404, "Item not found")

    db.delete(it)
    db.commit()

    return RedirectResponse(
        url="/admin/items/pending",
        status_code=status.HTTP_302_FOUND
    )
