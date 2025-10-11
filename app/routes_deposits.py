# app/routes_deposits.py
from __future__ import annotations
from typing import Optional, Literal, List, Dict
from datetime import datetime
import os
import io
import shutil
import stripe

from fastapi import (
    APIRouter,
    Depends,
    Request,
    HTTPException,
    Form,
    UploadFile,
    File,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
# ✅ [جديد] نستخدم or_ الصريحة
from sqlalchemy import or_

from .database import get_db
from .models import Booking, Item, User
from .notifications_api import push_notification, notify_admins

router = APIRouter(tags=["deposits"])

# ============ Stripe ============
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# ============ مسارات الأدلة (بدون تغيير قاعدة البيانات) ============
APP_ROOT = os.getenv("APP_ROOT", "/opt/render/project/src")  # آمن على Render
UPLOADS_BASE = os.path.join(APP_ROOT, "uploads")
DEPOSIT_UPLOADS = os.path.join(UPLOADS_BASE, "deposits")
os.makedirs(DEPOSIT_UPLOADS, exist_ok=True)

# ✅ [مهم] أضفنا HEIC/HEIF + دعم الامتدادات الشائعة
ALLOWED_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp4", ".mov", ".m4v", ".avi", ".wmv",
    ".heic", ".heif", ".bmp", ".tiff"
}

def _ext_ok(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTS

def _booking_folder(booking_id: int) -> str:
    path = os.path.join(DEPOSIT_UPLOADS, str(booking_id))
    os.makedirs(path, exist_ok=True)
    return path

def _save_evidence_files(booking_id: int, files: List[UploadFile] | None) -> List[str]:
    """يحفظ الملفات ويُعيد أسماء الملفات المحفوظة (فقط الاسم، بدون المسار الكامل)."""
    saved: List[str] = []
    if not files:
        return saved
    folder = _booking_folder(booking_id)
    for f in files:
        if not f or not f.filename:
            continue
        if not _ext_ok(f.filename):
            # نتجاهل الامتدادات غير المدعومة بصمت حتى لا نكسر التدفق
            continue
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        _, ext = os.path.splitext(f.filename)
        safe_name = f"{ts}{ext.lower()}"
        dest = os.path.join(folder, safe_name)
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        try:
            f.file.close()
        except Exception:
            pass
        saved.append(safe_name)
    return saved

def _list_evidence_files(booking_id: int) -> List[str]:
    """يُعيد قائمة أسماء الملفات الموجودة للقضية."""
    folder = _booking_folder(booking_id)
    try:
        files = [n for n in os.listdir(folder) if _ext_ok(n)]
        files.sort()
        return files
    except Exception:
        return []

def _evidence_urls(request: Request, booking_id: int) -> List[str]:
    """يبني روابط عامة للملفات عبر /uploads/... (يجب أن تكون لديك StaticFiles مركّبة على مجلد uploads)."""
    # في main.py لديك بالفعل تقديم uploads. إن لم يكن، أضِف:
    # app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
    base = f"/uploads/deposits/{booking_id}"
    return [f"{base}/{name}" for name in _list_evidence_files(booking_id)]


# ============ Helpers ============
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None

def require_auth(u: Optional[User]):
    if not u:
        raise HTTPException(status_code=401, detail="Unauthorized")

def require_booking(db: Session, booking_id: int) -> Booking:
    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    return bk

def can_manage_deposits(u: Optional[User]) -> bool:
    if not u:
        return False
    role = (getattr(u, "role", "") or "").lower()
    if role == "admin":
        return True
    return bool(getattr(u, "is_deposit_manager", False))


# ============ قائمة القضايا (DM) ============
@router.get("/dm/deposits")
def dm_queue(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    تعرض كل الحجوزات التي لديها وديعة محجوزة وتحتاج معالجة:
    - deposit_status in ('held','in_dispute','partially_withheld')
    - أو حالة الحجز تشير لعودة العنصر ومراجعة الوديعة ('returned','in_review')
    """
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    # ✅ [تعديل مهم] استخدم or_ بدلاً من عامل | لضمان التوافق الكامل
    q = (
        db.query(Booking)
        .filter(
            or_(
                Booking.deposit_hold_intent_id.isnot(None),
                Booking.deposit_status.in_(["held", "in_dispute", "partially_withheld"]),
                Booking.status.in_(["returned", "in_review"]),
            )
        )
        .order_by(Booking.updated_at.desc() if hasattr(Booking, "updated_at") else Booking.id.desc())
    )
    cases: List[Booking] = q.all()

    item_ids = {b.item_id for b in cases}
    items: List[Item] = db.query(Item).filter(Item.id.in_(item_ids)).all() if item_ids else []
    items_map: Dict[int, Item] = {it.id: it for it in items}

    return request.app.templates.TemplateResponse(
        "dm_queue.html",
        {
            "request": request,
            "title": "قضايا الوديعة",
            "session_user": request.session.get("user"),
            "cases": cases,
            "items_map": items_map,
        },
    )


# ============ صفحة القضية للمراجع/DM ============
@router.get("/dm/deposits/{booking_id}")
def dm_case_page(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    bk = require_booking(db, booking_id)
    item = db.get(Item, bk.item_id)

    # روابط الأدلة ليطلع عليها DM
    evidence = _evidence_urls(request, bk.id)

    return request.app.templates.TemplateResponse(
        "dm_case.html",
        {
            "request": request,
            "title": f"قضية وديعة #{bk.id}",
            "session_user": request.session.get("user"),
            "bk": bk,
            "booking": bk,          # لتوافق القوالب التي تتوقع 'booking'
            "item": item,
            "evidence": evidence,   # قائمة روابط لصور/فيديوهات البلاغ
        },
    )


# ============ تنفيذ القرار (DM) ============
@router.post("/dm/deposits/{booking_id}/decision")
def dm_decision(
    booking_id: int,
    decision: Literal["release", "withhold"] = Form(...),
    amount: int = Form(0),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    decision = release  -> إرجاع كامل (cancel authorization)
    decision = withhold -> إن كان amount == deposit  => خصم كامل
                           إن كان 0 < amount < deposit => خصم جزئي
    """
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    bk = require_booking(db, booking_id)
    pi_id = getattr(bk, "deposit_hold_intent_id", None)
    if not pi_id:
        return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

    deposit_total = max(0, bk.deposit_amount or bk.hold_deposit_amount or 0)

    try:
        if decision == "release":
            stripe.PaymentIntent.cancel(pi_id)
            bk.deposit_status = "refunded"
            bk.deposit_charged_amount = 0
            _audit(db, actor=user, bk=bk, action="deposit_release_all", details={"reason": reason})

        elif decision == "withhold":
            amt = max(0, int(amount or 0))
            if amt <= 0:
                raise HTTPException(status_code=400, detail="Invalid amount")
            if amt >= deposit_total:
                stripe.PaymentIntent.capture(pi_id, amount_to_capture=deposit_total * 100)
                bk.deposit_status = "claimed"
                bk.deposit_charged_amount = deposit_total
                _audit(db, actor=user, bk=bk, action="deposit_withhold_all", details={"amount": deposit_total, "reason": reason})
            else:
                stripe.PaymentIntent.capture(pi_id, amount_to_capture=amt * 100)
                bk.deposit_status = "partially_withheld"
                bk.deposit_charged_amount = amt
                _audit(db, actor=user, bk=bk, action="deposit_withhold_partial", details={"amount": amt, "reason": reason})
        else:
            raise HTTPException(status_code=400, detail="Unknown decision")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe deposit operation failed: {e}")

    bk.status = "closed"
    bk.updated_at = datetime.utcnow()
    if reason:
        try:
            setattr(bk, "owner_return_note", reason)
        except Exception:
            pass

    db.commit()

    push_notification(
        db, bk.owner_id, "قرار الوديعة", f"تم تنفيذ قرار الوديعة لحجز #{bk.id}.", f"/bookings/flow/{bk.id}", "deposit"
    )
    push_notification(
        db, bk.renter_id, "قرار الوديعة", f"صدر القرار النهائي بخصوص وديعة حجز #{bk.id}.", f"/bookings/flow/{bk.id}", "deposit"
    )
    notify_admins(db, "قرار وديعة مُنفَّذ", f"قرار {decision} لحجز #{bk.id}.", f"/bookings/flow/{bk.id}")

    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)


# ===================== [صفحة البلاغ + المعالجة] =====================

@router.get("/deposits/{booking_id}/report")
def report_deposit_issue_page(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """تعرض فورم بلاغ الوديعة للمالك مع رفع صور/فيديو ووصف."""
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can open report page")
    item = db.get(Item, bk.item_id)
    return request.app.templates.TemplateResponse(
        "deposit_report.html",
        {
            "request": request,
            "title": f"فتح بلاغ وديعة — حجز #{bk.id}",
            "session_user": request.session.get("user"),
            "bk": bk,
            "booking": bk,
            "item": item,
        },
    )


# 1) تسجيل تدقيقي اختياري
from sqlalchemy import text
from .database import engine as _engine

def _audit(db: Session, actor: Optional[User], bk: Booking, action: str, details: dict | None = None):
    """
    يكتب سجلًا في جدول deposit_audit_log إذا كان موجودًا.
    """
    try:
        with _engine.begin() as conn:
            try:
                conn.exec_driver_sql("SELECT 1 FROM deposit_audit_log LIMIT 1")
                has_table = True
            except Exception:
                has_table = False
            if not has_table:
                return
            conn.exec_driver_sql(
                """
                INSERT INTO deposit_audit_log (booking_id, actor_id, role, action, details, created_at)
                VALUES (:bid, :aid, :role, :action, :details, :ts)
                """,
                {
                    "bid": bk.id,
                    "aid": getattr(actor, "id", None),
                    "role": (getattr(actor, "role", "") or ("dm" if can_manage_deposits(actor) else "")),
                    "action": action,
                    "details": (str(details) if details else None),
                    "ts": datetime.utcnow(),
                },
            )
    except Exception:
        pass


# ==== NEW: إشعار كل مديري الوديعة ====
def notify_dms(db: Session, title: str, body: str = "", url: str = ""):
    """إشعار جميع مستخدمي MD + الإدمن."""
    dms = db.query(User).filter(
        (User.is_deposit_manager == True) | ((User.role or "") == "admin")
    ).all()
    for u in dms:
        push_notification(db, u.id, title, body, url, kind="deposit")


# 2) إرسال البلاغ (POST) — يحفظ الأدلة ويحوّل الحالة إلى in_dispute / in_review
@router.post("/deposits/{booking_id}/report")
def report_deposit_issue(
    booking_id: int,
    issue_type: Literal["delay", "damage", "loss", "theft"] = Form(...),
    description: str = Form(""),
    files: List[UploadFile] | None = File(None),  # ← صور/فيديوهات متعدّدة
    request: Request = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يستخدمه المالك لفتح قضية وديعة مع أدلة (ملفات).
    الأدلة تُحفظ على القرص، وتتحوّل الحالة ليظهر الحجز في قائمة DM.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can report issue")
    if getattr(bk, "deposit_hold_intent_id", None) is None:
        raise HTTPException(status_code=400, detail="No deposit hold found")

    # حفظ الأدلة
    saved = _save_evidence_files(bk.id, files)

    # تحديث حالات الحجز (تجعل القضية تظهر في /dm/deposits)
    bk.deposit_status = "in_dispute"
    bk.status = "in_review"
    bk.updated_at = datetime.utcnow()

    # ضمّ النص إلى ملاحظة المالك (إن وُجد العمود)
    try:
        note_old = (getattr(bk, "owner_return_note", "") or "").strip()
        note_new = f"[{issue_type}] {description}".strip()
        setattr(bk, "owner_return_note", (note_old + ("\n" if note_old and note_new else "") + note_new))
    except Exception:
        pass

    db.commit()

    # إشعارات
    push_notification(
        db,
        bk.renter_id,
        "بلاغ وديعة جديد",
        f"قام المالك بالإبلاغ عن مشكلة ({issue_type}) بخصوص الحجز #{bk.id}.",
        f"/bookings/flow/{bk.id}",
        "deposit"
    )
    notify_dms(db, "بلاغ وديعة جديد — بانتظار المراجعة",
               f"بلاغ جديد للحجز #{bk.id}.", f"/dm/deposits/{bk.id}")
    notify_admins(db, "مراجعة ديبو مطلوبة",
                  f"بلاغ جديد بخصوص حجز #{bk.id}.", f"/dm/deposits/{bk.id}")

    # سجل تدقيقي
    _audit(
        db,
        actor=user,
        bk=bk,
        action="owner_report_issue",
        details={"issue_type": issue_type, "desc": description, "files": saved},
    )

    # ✅ صفحة شكر بدل الرجوع لشاشة الزر
    return request.app.templates.TemplateResponse(
        "deposit_report_ok.html",
        {
            "request": request,
            "title": "تم إرسال البلاغ",
            "session_user": request.session.get("user"),
            "bk": bk,
        },
        status_code=200
    )


# 3) ردّ المستأجر على البلاغ (تعليق فقط)
@router.post("/deposits/{booking_id}/renter-response")
def renter_response_to_issue(
    booking_id: int,
    renter_comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """يتيح للمستأجر إضافة رده على بلاغ الوديعة."""
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can respond")
    if bk.deposit_status != "in_dispute":
        raise HTTPException(status_code=400, detail="No open deposit issue")

    try:
        setattr(bk, "updated_at", datetime.utcnow())
    except Exception:
        pass
    db.commit()

    push_notification(
        db,
        bk.owner_id,
        "رد من المستأجر",
        f"ردّ المستأجر على بلاغ الوديعة لحجز #{bk.id}.",
        f"/bookings/flow/{bk.id}",
        "deposit"
    )
    notify_admins(db, "رد وديعة جديد", f"ردّ المستأجر في قضية حجز #{bk.id}.", f"/dm/deposits/{bk.id}")

    _audit(db, actor=user, bk=bk, action="renter_response", details={"comment": renter_comment})

    return RedirectResponse(f"/bookings/flow/{bk.id}", status_code=303)


# 4) (اختياري) استلام/Claim القضية من متحكّم الوديعة
@router.post("/dm/deposits/{booking_id}/claim")
def dm_claim_case(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يضع المراجع الحالي كمُستلم للقضية إن كان لديك عمود dm_assignee_id في bookings.
    يتجاهل بهدوء إن لم يكن العمود موجودًا.
    """
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    bk = require_booking(db, booking_id)

    try:
        current = getattr(bk, "dm_assignee_id")
        if current in (None, 0):
            setattr(bk, "dm_assignee_id", user.id)
            setattr(bk, "updated_at", datetime.utcnow())
            _audit(db, actor=user, bk=bk, action="dm_claim_case", details={})
            db.commit()
    except Exception:
        pass

    return RedirectResponse(f"/dm/deposits/{bk.id}", status_code=303)