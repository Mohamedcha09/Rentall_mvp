# app/admin_items.py
from fastapi import APIRouter, Depends, Request, HTTPException, Form, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload
from datetime import datetime
import json

from .database import get_db
from .models import Item, MessageAttachment, MessageThread
from .message_attachments import (
    message_attachment_cleanup_reference,
    remove_saved_message_attachment_files,
)
from .notifications_api import push_notification
from .finder_service import remove_listing_index, sync_listing_index
from .catalog_taxonomy import listing_hierarchy, normalize_language, ui_copy

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


def _pending_item_images(item: Item) -> list[str]:
    """Normalize current ARRAY plus legacy JSON/CSV image values for display.

    This is presentation-only: it never rewrites the attachment/storage value
    and keeps a legacy ``image_path`` fallback for listings created before
    multi-image support.
    """
    raw = getattr(item, "image_urls", None)
    if isinstance(raw, (list, tuple)):
        images = [str(value).strip() for value in raw if str(value or "").strip()]
    elif isinstance(raw, str) and raw.strip():
        candidate = raw.strip()
        try:
            decoded = json.loads(candidate)
        except (TypeError, ValueError):
            decoded = None
        if isinstance(decoded, list):
            images = [str(value).strip() for value in decoded if str(value or "").strip()]
        else:
            images = [value.strip() for value in candidate.split(",") if value.strip()]
    else:
        images = []
    if not images and getattr(item, "image_path", None):
        images = [str(item.image_path).strip()]
    return images


# ==========================
# 1) LIST PENDING ITEMS
# ==========================
@router.get("/pending")
def list_pending(request: Request, db: Session = Depends(get_db)):
    require_admin(request)

    items = (
        db.query(Item)
        .options(selectinload(Item.owner))
        .filter(Item.status == "pending")
        .order_by(Item.created_at.asc())
        .all()
    )
    language = normalize_language(request.cookies.get("lang"))
    for item in items:
        item.taxonomy_hierarchy = listing_hierarchy(item, language)
        item.pending_image_urls = _pending_item_images(item)
    admin_copy = {
        key: ui_copy(key, language)
        for key in (
            "category", "subcategory", "type", "digital_type", "service", "service_platform",
            "pending_review", "pending_items_review", "pending_items_lead", "pending_count", "no_pending_items",
            "owner", "unknown", "email", "user_id", "account_type", "location", "price", "per_day",
            "listing_category_hierarchy", "image", "description", "images",
            "created", "no_images", "approve", "delete", "feedback", "send_feedback", "cancel", "delete_confirm",
        )
    }

    return request.app.templates.TemplateResponse(
        request=request,
        name="admin_items_pending.html",
        context={
            "request": request,
            "items": items,
            "pending_count": len(items),
            "admin_copy": admin_copy,
            "admin_language": language,
            "session_user": request.session.get("user"),
        }
    )


# ==========================
# 2) APPROVE ITEM
# ==========================
@router.post("/{item_id}/approve")
def approve_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)

    it = db.get(Item, item_id)
    if not it:
        raise HTTPException(404, "Item not found")

    it.status = "approved"
    it.reviewed_at = datetime.utcnow()
    it.admin_feedback = None
    # Write the public derived search document atomically with approval.
    sync_listing_index(db, it)
    db.commit()

    # إرسال إشعار قبول
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
@router.post("/{item_id}/reject")
def reject_item(item_id: int, request: Request, db: Session = Depends(get_db), feedback: str = Form("")):
    require_admin(request)

    it = db.get(Item, item_id)
    if not it:
        raise HTTPException(404, "Item not found")

    # تحديث الحالة
    it.status = "rejected"
    it.admin_feedback = feedback
    it.reviewed_at = datetime.utcnow()
    sync_listing_index(db, it)
    db.commit()

    # 🌟 إنشاء الإشعار بدون رابط
    notif = push_notification(
        db,
        user_id=it.owner_id,
        title="Your item was rejected",
        body=f"Your listing '{it.title}' requires changes.\nReason: {feedback}",
        url="",    
        kind="reject_edit"
    )

    # 🌟 إضافة الرابط الصحيح بعد الإنشاء — الآن معه notif.id + item_id
    notif.link_url = f"/notifications/open/{notif.id}?item_id={it.id}"
    db.commit()

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

    it = db.get(Item, item_id)
    if not it:
        raise HTTPException(404, "Item not found")

    it.status = "pending"
    it.admin_feedback = None
    it.reviewed_at = None
    sync_listing_index(db, it)
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

    it = db.get(Item, item_id)
    if not it:
        raise HTTPException(404, "Item not found")

    # Item deletion cascades its direct-message threads.  Their database rows
    # clean up through the existing relationships, but private attachment bytes
    # live outside the database and must be removed only after that transaction
    # succeeds.
    thread_ids = [
        row[0]
        for row in db.query(MessageThread.id)
        .filter(MessageThread.item_id == it.id)
        .all()
    ]
    attachment_cleanup = (
        [
            message_attachment_cleanup_reference(attachment)
            for attachment in db.query(MessageAttachment)
            .filter(MessageAttachment.thread_id.in_(thread_ids))
            .all()
        ]
        if thread_ids
        else []
    )

    remove_listing_index(db, it.id)
    db.delete(it)
    db.commit()
    remove_saved_message_attachment_files(attachment_cleanup)

    return RedirectResponse(
        url="/admin/items/pending",
        status_code=status.HTTP_302_FOUND
    )
