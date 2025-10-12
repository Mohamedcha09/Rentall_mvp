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
# ✅ نستخدم or_ الصريحة
from sqlalchemy import or_

from .database import get_db
from .models import Booking, Item, User
from .notifications_api import push_notification, notify_admins

router = APIRouter(tags=["deposits"])

# ============ Stripe ============
# نحاول أخذ المفتاح من البيئة؛ وإن كان فارغًا نحمّل .env بشكل احتياطي
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
if not stripe.api_key:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
    except Exception:
        pass

# ============ مسارات الأدلة ============
# توحيد الجذر ليكون: <جذر المشروع>/uploads/deposits
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOADS_BASE = os.path.join(APP_ROOT, "uploads")
DEPOSIT_UPLOADS = os.path.join(UPLOADS_BASE, "deposits")
os.makedirs(DEPOSIT_UPLOADS, exist_ok=True)

# ✅ دعم الامتدادات الشائعة
ALLOWED_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp4", ".mov", ".m4v", ".avi", ".wmv",
    ".heic", ".heif", ".bmp", ".tiff"
}

def _ext_ok(filename: str) -> bool:
    _, ext = os.path.splitext((filename or "").lower())
    return ext in ALLOWED_EXTS

# ======================
# 🔧 تصحيح رئيسي هنا:
# بدل الاعتماد على ثابت DEPOSIT_UPLOADS فقط، نحسب مسار المجلد ديناميكيًا
# من __file__ في كل مرة (تمامًا كما يعمل debug/uploads).
# ======================
def _booking_folder(booking_id: int) -> str:
    """
    ابنِ المسار كل مرة من __file__ لضمان التطابق مع الماونت في main.py:
    ../uploads/deposits/<booking_id>
    """
    app_root_runtime = os.path.dirname(os.path.dirname(__file__))   # ../src
    uploads_base_rt  = os.path.join(app_root_runtime, "uploads")    # ../src/uploads
    deposits_dir_rt  = os.path.join(uploads_base_rt, "deposits")    # ../src/uploads/deposits
    os.makedirs(deposits_dir_rt, exist_ok=True)
    path = os.path.join(deposits_dir_rt, str(booking_id))
    os.makedirs(path, exist_ok=True)
    return path

def _save_evidence_files(booking_id: int, files: List[UploadFile] | None) -> List[str]:
    """يحفظ الملفات ويُعيد أسماء الملفات المحفوظة."""
    saved: List[str] = []
    if not files:
        return saved
    folder = _booking_folder(booking_id)
    for f in files:
        if not f or not f.filename:
            continue
        if not _ext_ok(f.filename):
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
    """
    أرجع كل الملفات الموجودة داخل مجلد القضية بدون أي فلترة،
    حتى نتأكد أن القراءة صحيحة 100%. لاحقًا ممكن نرجع نفلتر.
    """
    folder = _booking_folder(booking_id)
    try:
        names = []
        for entry in os.scandir(folder):
            if entry.is_file():
                names.append(entry.name)
        names.sort()
        print(f"[evidence] FOUND in {folder}: {names}")
        return names
    except Exception as e:
        print(f"[evidence] ERROR reading {folder}: {e}")
        return []

def _evidence_urls(request: Request, booking_id: int) -> List[str]:
    base = f"/uploads/deposits/{booking_id}"
    files = _list_evidence_files(booking_id)
    urls = [f"{base}/{name}" for name in files]
    print(f"[evidence] URLS for #{booking_id}: {urls}")
    return urls


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
    تعرض كل الحجوزات التي تحتاج مراجعة وديعة:
    - deposit_status in ('held','in_dispute','partially_withheld')
    - أو حالة الحجز تشير لعودة العنصر ومراجعة الوديعة ('returned','in_review')
    """
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    # لا نحذف أي شرط — فقط نضمن OR كافية
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


# ============ صفحة القضية للمراجع ============
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
    evidence = _evidence_urls(request, bk.id)

    return request.app.templates.TemplateResponse(
        "dm_case.html",
        {
            "request": request,
            "title": f"قضية وديعة #{bk.id}",
            "session_user": request.session.get("user"),
            "bk": bk,
            "booking": bk,
            "item": item,
            "evidence": evidence,
        },
    )


# ============ تنفيذ القرار ============
@router.post("/dm/deposits/{booking_id}/decision")
def dm_decision(
    booking_id: int,
    decision: Literal["release", "withhold"] = Form(...),
    amount: int = Form(0),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
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


# ===================== بلاغ الوديعة =====================
@router.get("/deposits/{booking_id}/report")
def report_deposit_issue_page(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
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


# ==== سجل تدقيقي ====
from sqlalchemy import text
from .database import engine as _engine

def _audit(db: Session, actor: Optional[User], bk: Booking, action: str, details: dict | None = None):
    """
    نحاول الكتابة في جدول السجل؛ إن كان اسم الجدول مفردًا أو جمعًا.
    لا نحذف منطقك القديم، نضيف فحصًا إضافيًا فقط.
    """
    try:
        with _engine.begin() as conn:
            has_table = False
            try:
                conn.exec_driver_sql("SELECT 1 FROM deposit_audit_log LIMIT 1")
                table_name = "deposit_audit_log"
                has_table = True
            except Exception:
                try:
                    conn.exec_driver_sql("SELECT 1 FROM deposit_audit_logs LIMIT 1")
                    table_name = "deposit_audit_logs"
                    has_table = True
                except Exception:
                    has_table = False

            if not has_table:
                return

            conn.exec_driver_sql(
                f"""
                INSERT INTO {table_name} (booking_id, actor_id, role, action, details, created_at)
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


# ==== إشعار مديري الوديعة ====
def notify_dms(db: Session, title: str, body: str = "", url: str = ""):
    dms = db.query(User).filter(
        (User.is_deposit_manager == True) | ((User.role or "") == "admin")
    ).all()
    for u in dms:
        push_notification(db, u.id, title, body, url, kind="deposit")


# ==== إرسال البلاغ ====
@router.post("/deposits/{booking_id}/report")
def report_deposit_issue(
    booking_id: int,
    issue_type: Literal["delay", "damage", "loss", "theft"] = Form(...),
    description: str = Form(""),
    files: List[UploadFile] | None = File(None),
    request: Request = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can report issue")
    if getattr(bk, "deposit_hold_intent_id", None) is None:
        raise HTTPException(status_code=400, detail="No deposit hold found")

    saved = _save_evidence_files(bk.id, files)
    bk.deposit_status = "in_dispute"
    bk.status = "in_review"
    bk.updated_at = datetime.utcnow()

    try:
        note_old = (getattr(bk, "owner_return_note", "") or "").strip()
        note_new = f"[{issue_type}] {description}".strip()
        setattr(bk, "owner_return_note", (note_old + ("\n" if note_old and note_new else "") + note_new))
    except Exception:
        pass

    db.commit()

    push_notification(db, bk.renter_id, "بلاغ وديعة جديد", f"قام المالك بالإبلاغ عن مشكلة ({issue_type}) بخصوص الحجز #{bk.id}.", f"/bookings/flow/{bk.id}", "deposit")
    notify_dms(db, "بلاغ وديعة جديد — بانتظار المراجعة", f"بلاغ جديد للحجز #{bk.id}.", f"/dm/deposits/{bk.id}")
    notify_admins(db, "مراجعة ديبو مطلوبة", f"بلاغ جديد بخصوص حجز #{bk.id}.", f"/dm/deposits/{bk.id}")

    _audit(db, actor=user, bk=bk, action="owner_report_issue", details={"issue_type": issue_type, "desc": description, "files": saved})

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


# ==== ردّ المستأجر ====
@router.post("/deposits/{booking_id}/renter-response")
def renter_response_to_issue(
    booking_id: int,
    renter_comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
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

    push_notification(db, bk.owner_id, "رد من المستأجر", f"ردّ المستأجر على بلاغ الوديعة لحجز #{bk.id}.", f"/bookings/flow/{bk.id}", "deposit")
    notify_admins(db, "رد وديعة جديد", f"ردّ المستأجر في قضية حجز #{bk.id}.", f"/dm/deposits/{bk.id}")

    _audit(db, actor=user, bk=bk, action="renter_response", details={"comment": renter_comment})

    return RedirectResponse(f"/dm/deposits/{bk.id}", status_code=303)


# ==== استلام القضية ====
@router.post("/dm/deposits/{booking_id}/claim")
def dm_claim_case(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    bk = require_booking(db, booking_id)

    try:
        current = getattr(bk, "dm_assignee_id", None)
        if current in (None, 0):
            setattr(bk, "dm_assignee_id", user.id)
            setattr(bk, "updated_at", datetime.utcnow())
            _audit(db, actor=user, bk=bk, action="dm_claim_case", details={})
            db.commit()
    except Exception:
        pass

    return RedirectResponse(f"/dm/deposits/{bk.id}", status_code=303)


# ===== DEBUG: افحص مسارات الرفع والقراءة على الديبلوي (Top-level, ليس داخل دالة) =====
@router.get("/debug/uploads/{booking_id}")
def debug_uploads(booking_id: int, request: Request):
    APP_ROOT_RT = os.path.dirname(os.path.dirname(__file__))
    UPLOADS_BASE_RT = os.path.join(APP_ROOT_RT, "uploads")
    DEPOSIT_UPLOADS_RT = os.path.join(UPLOADS_BASE_RT, "deposits")
    bk_folder = os.path.join(DEPOSIT_UPLOADS_RT, str(booking_id))
    os.makedirs(bk_folder, exist_ok=True)

    # أنشئ ملف اختبار صغير داخل مجلد القضية
    test_path = os.path.join(bk_folder, "test.txt")
    if not os.path.exists(test_path):
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("OK " + datetime.utcnow().isoformat())

    return {
        "app_root": APP_ROOT_RT,
        "uploads_base": UPLOADS_BASE_RT,
        "deposits_dir": DEPOSIT_UPLOADS_RT,
        "booking_folder": bk_folder,
        "folder_exists": os.path.isdir(bk_folder),
        "files_now": sorted(os.listdir(bk_folder)),
        "public_url_example": f"/uploads/deposits/{booking_id}/test.txt"
    }

# ===== Debug إضافية لعرض ما تراه صفحة القضية بالضبط =====
@router.get("/debug/evidence/{booking_id}")
def debug_evidence(booking_id: int, request: Request):
    return {"urls": _evidence_urls(request, booking_id)}

@router.get("/debug/file/{booking_id}/{name}")
def debug_open_file(booking_id: int, name: str):
    return {"public_url": f"/uploads/deposits/{booking_id}/{name}"}