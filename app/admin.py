from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Document, MessageThread, Message

router = APIRouter()


# ---------------------------
# Helpers
# ---------------------------
def require_admin(request: Request) -> bool:
    u = request.session.get("user")
    return bool(u and u.get("role") == "admin")


def _open_or_create_admin_thread(db: Session, admin_id: int, user_id: int) -> MessageThread:
    """افتح أو أنشئ خيط رسائل بين الأدمِن والمستخدم."""
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
    """لو الأدمِن عدّل نفسه، حدّث القيم داخل session حتى تظهر فورًا في الواجهة."""
    sess = request.session.get("user")
    if not sess:
        return
    if sess.get("id") != user.id:
        return
    # قيَم شائعة نحتاجها في القوالب
    sess["role"] = user.role
    sess["status"] = user.status
    sess["is_verified"] = bool(user.is_verified)
    # إن كانت أعمدة الشارات موجودة سيتم قراءتها (وإلا ستُهمل تلقائيًا)
    for k in [
        "badge_admin", "badge_new_yellow", "badge_pro_green", "badge_pro_gold",
        "badge_purple_trust", "badge_renter_green", "badge_orange_stars",
    ]:
        if hasattr(user, k):
            sess[k] = getattr(user, k)
    # صلاحية متحكّم الوديعة
    if hasattr(user, "is_deposit_manager"):
        sess["is_deposit_manager"] = bool(getattr(user, "is_deposit_manager", False))


# ---------------------------
# لوحة الأدمِن
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
            "title": "لوحة الأدمين",
            "pending_users": pending_users,
            "all_users": all_users,
            "session_user": request.session.get("user"),
        },
    )


# ---------------------------
# قرارات التسجيل
# ---------------------------
@router.post("/admin/users/{user_id}/approve")
def approve_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if user:
        user.status = "approved"
        # وافِق على وثائقه إن وُجدت
        for d in (user.documents or []):
            d.review_status = "approved"
            d.reviewed_at = datetime.utcnow()
        db.commit()
        _refresh_session_user_if_self(request, user)

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/reject")
def reject_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if user:
        user.status = "rejected"
        for d in (user.documents or []):
            d.review_status = "rejected"
            d.reviewed_at = datetime.utcnow()
        db.commit()
        _refresh_session_user_if_self(request, user)

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# التوثيق (Verification)
# ---------------------------
@router.post("/admin/users/{user_id}/verify")
def verify_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    user = db.query(User).get(user_id)
    if user:
        user.is_verified = True
        user.verified_at = datetime.utcnow()
        # verified_by_id قد لا يكون موجودًا في DB قديمة؛ إن كان موجودًا سيُخزَّن تلقائيًا
        if hasattr(user, "verified_by_id"):
            user.verified_by_id = admin["id"]
        db.commit()
        _refresh_session_user_if_self(request, user)

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/unverify")
def unverify_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if user:
        user.is_verified = False
        if hasattr(user, "verified_at"):
            user.verified_at = None
        if hasattr(user, "verified_by_id"):
            user.verified_by_id = None
        db.commit()
        _refresh_session_user_if_self(request, user)

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# مراجعة وثائق فردية (اختياري)
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
# مراسلة المستخدم + طلب تصحيح
# ---------------------------
@router.post("/admin/users/{user_id}/message")
def admin_message_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """إنشاء/فتح محادثة مع المستخدم ثم تحويل لصفحة الرسائل."""
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    if not admin:
        return RedirectResponse(url="/login", status_code=303)

    thread = _open_or_create_admin_thread(db, admin["id"], user_id)

    # رسالة افتتاحية إذا كان الخيط بدون رسائل
    first_msg = db.query(Message).filter(Message.thread_id == thread.id).first()
    if not first_msg:
        db.add(Message(thread_id=thread.id, sender_id=admin["id"], body="مرحبًا! يرجى استكمال/تصحيح بيانات التحقق."))
        db.commit()

    return RedirectResponse(url=f"/messages/{thread.id}", status_code=303)


@router.post("/admin/users/{user_id}/request_fix")
def admin_request_fix(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    reason: str = Form("نحتاج صورة أوضح أو وثيقة صالحة.")
):
    """يضع حالة الوثائق إلى needs_fix ويرسل سببًا في الرسائل مع رابط التصحيح."""
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
    body = f"مرحبًا {user.first_name}،\nهناك ملاحظات على مستندات التحقق:\n- {reason}\nيرجى التصحيح هنا: {fix_link}"
    db.add(Message(thread_id=thread.id, sender_id=admin["id"], body=body))
    db.commit()

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# إدارة الشارات (Badges)
# ---------------------------
@router.post("/users/{user_id}/badges")
def set_badges(
    user_id: int,
    badge_purple_trust: str | None = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if not u:
        return RedirectResponse(url="/admin", status_code=303)

    # البنفسجي فقط
    u.badge_purple_trust = bool(badge_purple_trust)

    # لو أردت ربطها مباشرة بـ is_verified أيضًا:
    u.is_verified = u.badge_purple_trust

    db.add(u)
    db.commit()
    db.refresh(u)

    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------
# (NEW) إدارة صلاحية متحكّم الوديعة
# ---------------------------
@router.post("/admin/users/{user_id}/deposit_manager/enable")
def enable_deposit_manager(user_id: int, request: Request, db: Session = Depends(get_db)):
    """يمنح المستخدم صلاحية متحكّم الوديعة (يمكنه حسم/رد الوديعة)."""
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_deposit_manager"):
        u.is_deposit_manager = True
        db.commit()
        _refresh_session_user_if_self(request, u)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/deposit_manager/disable")
def disable_deposit_manager(user_id: int, request: Request, db: Session = Depends(get_db)):
    """يلغي صلاحية متحكّم الوديعة عن المستخدم."""
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u and hasattr(u, "is_deposit_manager"):
        u.is_deposit_manager = False
        db.commit()
        _refresh_session_user_if_self(request, u)
    return RedirectResponse(url="/admin", status_code=303)
