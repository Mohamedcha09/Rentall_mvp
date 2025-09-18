# app/admin.py
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from .database import get_db
from .models import User, Document, MessageThread, Message  # ← أضفنا MessageThread, Message

router = APIRouter()

def require_admin(request: Request) -> bool:
    u = request.session.get("user")
    return bool(u and u.get("role") == "admin")

@router.get("/admin")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """
    لوحة الأدمين:
    - قائمة المستخدمين قيد المراجعة (status = pending)
    - لمحة عن جميع المستخدمين لتسهيل التوثيق/إلغاءه
    """
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    pending_users = (
        db.query(User)
        .filter(User.status == "pending")
        .order_by(User.created_at.desc())
        .all()
    )

    # جميع المستخدمين
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

# ---------- قرارات التسجيل ----------
@router.post("/admin/users/{user_id}/approve")
def approve_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if user:
        user.status = "approved"
        db.commit()
        # تحديث وثائق المستخدم للموافقة (إن وُجدت)
        for d in user.documents:
            d.review_status = "approved"
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)

@router.post("/admin/users/{user_id}/reject")
def reject_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if user:
        user.status = "rejected"
        db.commit()
        # رفض الوثائق أيضًا
        for d in user.documents:
            d.review_status = "rejected"
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)

# ---------- التوثيق (Verification) ----------
@router.post("/admin/users/{user_id}/verify")
def verify_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    user = db.query(User).get(user_id)
    if user:
        user.is_verified = True
        user.verified_at = datetime.utcnow()
        user.verified_by_id = admin["id"]
        db.commit()

        # لو الذي تمّ توثيقه هو المستخدم الحالي، حدّث الـ session
        if request.session.get("user", {}).get("id") == user.id:
            request.session["user"]["is_verified"] = True

    return RedirectResponse(url="/admin", status_code=303)

@router.post("/admin/users/{user_id}/unverify")
def unverify_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if user:
        user.is_verified = False
        user.verified_at = None
        user.verified_by_id = None
        db.commit()

        # حدّث session إن كان هذا هو نفس المستخدم المسجّل حاليًا
        if request.session.get("user", {}).get("id") == user.id:
            request.session["user"]["is_verified"] = False

    return RedirectResponse(url="/admin", status_code=303)

# ---------- مراجعة وثائق فردية (اختياري) ----------
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

# ---------- مساعد داخلي: افتح أو أنشئ خيط رسائل بين الأدمِن والمستخدم ----------
def _open_or_create_admin_thread(db: Session, admin_id: int, user_id: int) -> MessageThread:
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

# ---------- جديد: فتح/إنشاء محادثة مع المستخدم ----------
@router.post("/admin/users/{user_id}/message")
def admin_message_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """
    ينشئ (أو يفتح إن كانت موجودة) محادثة خاصة بين الأدمِن والمستخدم المحدد،
    ثم يعيد التوجيه إلى صفحة المحادثة.
    """
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    if not admin:
        return RedirectResponse(url="/login", status_code=303)

    a_id = admin["id"]
    b_id = user_id

    thread = _open_or_create_admin_thread(db, a_id, b_id)

    # أرسل رسالة افتتاحية اختيارية إن كان الخيط جديد (لا رسائل)
    first_msg = db.query(Message).filter(Message.thread_id == thread.id).first()
    if not first_msg:
        msg = Message(thread_id=thread.id, sender_id=a_id, body="مرحبًا! يرجى استكمال/تصحيح بيانات التحقق.")
        db.add(msg)
        db.commit()

    return RedirectResponse(url=f"/messages/{thread.id}", status_code=303)

# ---------- جديد: طلب تصحيح بيانات/صور من المستخدم + رسالة تلقائية ----------
@router.post("/admin/users/{user_id}/request_fix")
def admin_request_fix(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    reason: str = Form("نحتاج صورة أوضح أو وثيقة صالحة.")  # سبب افتراضي لو ما كتب الأدمِن شيء
):
    """
    يضع ملاحظة المراجعة على وثائق المستخدم كـ needs_fix،
    ويرسل له رسالة خاصة بالسبب مع رابط صفحة تعديل بياناته.
    """
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    admin = request.session.get("user")
    if not admin:
        return RedirectResponse(url="/login", status_code=303)
    a_id = admin["id"]

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=303)

    # حدّث حالة وثائقه إلى needs_fix + ضع الملاحظة
    for d in user.documents:
        d.review_status = "needs_fix"
        # اجمع الملاحظات (لو صار فيه أكثر من طلب سابق)
        if d.review_note:
            d.review_note = f"{d.review_note.strip()}\n- {reason.strip()}"
        else:
            d.review_note = reason.strip()
        d.reviewed_at = datetime.utcnow()
    # اترك status المستخدم كما هو (عادة pending) — الفكرة أنه ما زال قيد المعالجة
    db.commit()

    # افتح/أنشئ محادثة وأرسل رسالة فيها السبب + رابط صفحة التعديل
    thread = _open_or_create_admin_thread(db, a_id, user_id)
    fix_link = "/profile/docs"  # صفحة تعديل/إعادة رفع المستندات (سنضيفها بالقالب)
    body = f"مرحبًا {user.first_name}،\nهناك ملاحظات على مستندات التحقق:\n- {reason}\nيرجى التصحيح وإعادة الإرسال هنا: {fix_link}"
    db.add(Message(thread_id=thread.id, sender_id=a_id, body=body))
    db.commit()

    return RedirectResponse(url="/admin", status_code=303)
