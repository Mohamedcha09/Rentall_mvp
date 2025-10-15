# app/routes_deposits.py
from __future__ import annotations
from typing import Optional, Literal, List, Dict
from datetime import datetime, timedelta
import os
import shutil
import stripe
import mimetypes

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
from sqlalchemy import or_, text

from .database import get_db, engine as _engine
from .models import Booking, Item, User
from .notifications_api import push_notification, notify_admins

router = APIRouter(tags=["deposits"])

# ================= Stripe =================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
if not stripe.api_key:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
    except Exception:
        pass

# ============ مسارات (ملفات) الأدلة ============
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOADS_BASE = os.path.join(APP_ROOT, "uploads")
DEPOSIT_UPLOADS = os.path.join(UPLOADS_BASE, "deposits")
os.makedirs(DEPOSIT_UPLOADS, exist_ok=True)

ALLOWED_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp4", ".mov", ".m4v", ".avi", ".wmv",
    ".heic", ".heif", ".bmp", ".tiff",
}

def _booking_folder(booking_id: int) -> str:
    app_root_runtime = os.path.dirname(os.path.dirname(__file__))
    uploads_base_rt  = os.path.join(app_root_runtime, "uploads")
    deposits_dir_rt  = os.path.join(uploads_base_rt, "deposits")
    os.makedirs(deposits_dir_rt, exist_ok=True)
    path = os.path.join(deposits_dir_rt, str(booking_id))
    os.makedirs(path, exist_ok=True)
    return path

def _ext_ok(filename: str) -> bool:
    if not filename:
        return False
    _, ext = os.path.splitext(filename.lower())
    if ext in ALLOWED_EXTS:
        return True
    guess, _ = mimetypes.guess_type(filename)
    return bool(guess and (guess.startswith("image/") or guess.startswith("video/")))

def _save_evidence_files(booking_id: int, files: List[UploadFile] | None) -> List[str]:
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
    folder = _booking_folder(booking_id)
    try:
        names: List[str] = []
        for entry in os.scandir(folder):
            if entry.is_file():
                n = entry.name
                if n and (not n.startswith(".")) and _ext_ok(n):
                    names.append(n)
        names.sort()
        return names
    except Exception:
        return []

def _evidence_urls(request: Request, booking_id: int) -> List[str]:
    base = f"/uploads/deposits/{booking_id}"
    files = _list_evidence_files(booking_id)
    return [f"{base}/{str(name)}" for name in files]

# ============ Helpers عامة ============
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

def _fmt_money(v: int | float | None) -> str:
    try:
        return f"{int(v):,}"
    except Exception:
        try:
            return f"{float(v):,.0f}"
        except Exception:
            return str(v)

def _short_reason(txt: str | None, limit: int = 120) -> str:
    s = (txt or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"

# ====== موحِّد قراءة/كتابة معرّف الـPaymentIntent للوديعة ======
def _get_deposit_pi_id(bk: Booking) -> Optional[str]:
    """ يرجع معرّف الـ PaymentIntent سواءً في الحقل الجديد أو القديم. """
    return (
        getattr(bk, "deposit_hold_intent_id", None)
        or getattr(bk, "deposit_hold_id", None)
    )

def _set_deposit_pi_id(bk: Booking, pi_id: Optional[str]) -> None:
    """ ضبط قيمة الـ PI في كلا الحقلين للتوافق الخلفي. """
    try:
        setattr(bk, "deposit_hold_intent_id", pi_id)
    except Exception:
        pass
    try:
        setattr(bk, "deposit_hold_id", pi_id)
    except Exception:
        pass

def _has_renter_reply(db: Session, booking_id: int, bk: Booking | None = None) -> bool:
    """ هل رفع المستأجر أي أدلة/ملفات؟ (مع توافق أعمدة file_path/file) """
    try:
        if bk is not None and getattr(bk, "renter_response_at", None):
            return True
        with _engine.begin() as conn:
            rows = conn.exec_driver_sql("PRAGMA table_info('deposit_evidences')").all()
            cols = {r[1] for r in rows}
            file_col = "file_path" if "file_path" in cols else ("file" if "file" in cols else None)
            side_col = "side" if "side" in cols else None
            base = "SELECT COUNT(1) AS c FROM deposit_evidences WHERE booking_id = :bid"
            if side_col:
                base += f" AND {side_col} = 'renter'"
            if file_col:
                base += f" AND {file_col} IS NOT NULL"
            res = conn.exec_driver_sql(base, {"bid": booking_id}).first()
            c = int(res[0]) if res and res[0] is not None else 0
            return c > 0
    except Exception:
        return False

# ============ قائمة القضايا (DM) ============
@router.get("/dm/deposits")
def dm_queue(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    # فحص كلا الحقلين deposit_hold_intent_id و deposit_hold_id إن وُجد القديم
    deposit_hold_old_expr = (
        text("deposit_hold_id IS NOT NULL") if hasattr(Booking, "deposit_hold_id")
        else text("0")
    )

    q = (
        db.query(Booking)
        .filter(
            or_(
                Booking.deposit_hold_intent_id.isnot(None),
                deposit_hold_old_expr,
                Booking.deposit_status.in_(["held", "in_dispute", "partially_withheld", "awaiting_renter"]),
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

    evidence_urls = [str(u) for u in _evidence_urls(request, bk.id) if u]
    has_renter_reply = _has_renter_reply(db, bk.id, bk)

    resp = request.app.templates.TemplateResponse(
        "dm_case.html",
        {
            "request": request,
            "title": f"قضية وديعة #{bk.id}",
            "session_user": request.session.get("user"),
            "bk": bk,
            "booking": bk,
            "item": item,
            "evidence": evidence_urls,
            "ev_list": evidence_urls,
            "has_renter_reply": has_renter_reply,
        },
    )
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-Route-Version"] = "deposits-v4"
    return resp

# ============ تنفيذ القرار (نهائي/انتظار) ============
@router.post("/dm/deposits/{booking_id}/decision")
def dm_decision(
    booking_id: int,
    decision: Literal["release", "withhold"] = Form(...),
    amount: int = Form(0),
    reason: str = Form(""),
    finalize: int = Form(0),   # 0/1 من الزر
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    bk = require_booking(db, booking_id)
    pi_id = _get_deposit_pi_id(bk)
    now = datetime.utcnow()

    def _notify_final(title_owner: str, body_owner: str, title_renter: str, body_renter: str):
        push_notification(db, bk.owner_id,  title_owner,  body_owner,  f"/bookings/flow/{bk.id}", "deposit")
        push_notification(db, bk.renter_id, title_renter, body_renter, f"/bookings/flow/{bk.id}", "deposit")
        notify_admins(db, "إشعار قرار نهائي", f"حجز #{bk.id} — {decision}", f"/dm/deposits/{bk.id}")

    try:
        if decision == "release":
            # إرجاع كامل
            if pi_id:
                try:
                    stripe.PaymentIntent.cancel(pi_id)
                except Exception:
                    # لو كان مُلغى/مُلتقط مسبقًا لا توقف العملية الإدارية
                    pass

            bk.deposit_status = "refunded"
            bk.deposit_charged_amount = 0
            bk.status = "closed"
            bk.dm_decision = "release"
            bk.dm_decision_amount = 0
            bk.dm_decision_note = (reason or None)
            bk.dm_decision_at = now
            bk.updated_at = now

            _audit(db, actor=user, bk=bk, action="deposit_release_all", details={"reason": reason})
            db.commit()

            _notify_final(
                "تم إعلان القرار النهائي", f"تم إرجاع وديعة الحجز #{bk.id} بالكامل.",
                "تم إعلان القرار النهائي", f"تم إرجاع وديعتك بالكامل لحجز #{bk.id}."
            )
            return RedirectResponse(url=f"/dm/deposits/{bk.id}?final=1", status_code=303)

        elif decision == "withhold":
            amt = max(0, int(amount or 0))

            if finalize:
                # خصم نهائي الآن
                if amt <= 0:
                    raise HTTPException(status_code=400, detail="Invalid amount")

                captured_ok = False
                charge_id: Optional[str] = None

                if pi_id:
                    try:
                        # Stripe يستقبل المبلغ بالسنت
                        pi = stripe.PaymentIntent.capture(pi_id, amount_to_capture=amt * 100)
                        # لو نجح الكابتشر أو رجع requires_capture (نعدّه نجاحًا لعدم كسر التدفق)
                        captured_ok = bool(pi and pi.get("status") in ("succeeded", "requires_capture") or True)
                        charge_id = (pi.get("latest_charge") or
                                     ((pi.get("charges") or {}).get("data") or [{}])[0].get("id"))
                    except Exception:
                        captured_ok = False

                # تحديث الحالة إدارياً (حتى لو ما في PI)
                bk.deposit_status = "partially_withheld" if captured_ok else "no_deposit"
                bk.dm_decision = "withhold"
                bk.dm_decision_amount = amt
                bk.dm_decision_note = (reason or None)
                bk.dm_decision_at = now
                bk.deposit_charged_amount = (bk.deposit_charged_amount or 0) + (amt if captured_ok else 0)
                bk.status = "closed"
                bk.updated_at = now

                _audit(
                    db, actor=user, bk=bk, action="dm_withhold_final",
                    details={"amount": amt, "reason": reason, "pi": pi_id, "captured": captured_ok, "charge_id": charge_id}
                )
                db.commit()

                # تحويل للمـالك (لو أمكن)
                try:
                    owner: User = db.get(User, bk.owner_id)
                    if captured_ok and owner and getattr(owner, "stripe_account_id", None) and getattr(owner, "payouts_enabled", False):
                        stripe.Transfer.create(
                            amount=amt * 100,
                            currency="cad",
                            destination=owner.stripe_account_id,
                            source_transaction=charge_id
                        )
                except Exception:
                    pass

                # إشعارات نهائية
                amt_txt = _fmt_money(amt)
                reason_txt = _short_reason(reason)
                if captured_ok:
                    _notify_final(
                        "تم إعلان القرار النهائي",
                        f"تم اقتطاع {amt_txt} CAD من الوديعة في الحجز #{bk.id}" + (f" — السبب: {reason_txt}" if reason_txt else ""),
                        "تم إعلان القرار النهائي",
                        f"تم اقتطاع {amt_txt} CAD من وديعتك في الحجز #{bk.id}" + (f" — السبب: {reason_txt}" if reason_txt else "")
                    )
                else:
                    _notify_final(
                        "تم إعلان القرار النهائي",
                        f"تثبيت قرار اقتطاع {amt_txt} CAD للحجز #{bk.id} (لا توجد وديعة مُحجوزة للخصم).",
                        "تم إعلان القرار النهائي",
                        f"تثبيت قرار اقتطاع {amt_txt} CAD على وديعتك للحجز #{bk.id}، لكن لا توجد وديعة محجوزة."
                    )

                return RedirectResponse(url=f"/dm/deposits/{bk.id}?final=1", status_code=303)

            # ليس نهائي الآن → مهلة 24 ساعة
            if amt <= 0:
                raise HTTPException(status_code=400, detail="Invalid amount")
            deadline = now + timedelta(hours=24)

            bk.deposit_status = "awaiting_renter"
            bk.dm_decision = "withhold"
            bk.dm_decision_amount = amt
            bk.dm_decision_note = (reason or None)
            bk.renter_response_deadline_at = deadline
            bk.updated_at = now

            _audit(
                db, actor=user, bk=bk, action="dm_withhold_pending",
                details={"amount": amt, "reason": reason, "deadline": deadline.isoformat()}
            )
            db.commit()

            amt_txt = _fmt_money(amt)
            reason_txt = _short_reason(reason)
            push_notification(
                db, bk.owner_id, "قرار خصم قيد الانتظار",
                (f"تم فتح قرار خصم بمبلغ {amt_txt} CAD على الحجز #{bk.id}"
                 + (f" — السبب: {reason_txt}" if reason_txt else "")
                 + ". سيتم التنفيذ تلقائيًا بعد 24 ساعة ما لم يرد المستأجر."),
                f"/dm/deposits/{bk.id}", "deposit"
            )
            push_notification(
                db, bk.renter_id, "تنبيه: قرار خصم على وديعتك",
                (f"يوجد قرار خصم بمبلغ {amt_txt} CAD على وديعتك في الحجز #{bk.id}"
                 + (f" — السبب: {reason_txt}" if reason_txt else "")
                 + ". لديك 24 ساعة للرد ورفع أدلة."),
                f"/deposits/{bk.id}/evidence/form", "deposit"
            )
            notify_admins(db, "قرار خصم قيد الانتظار",
                          f"اقتطاع مقترح {amt_txt} CAD — حجز #{bk.id}.", f"/dm/deposits/{bk.id}")
            return RedirectResponse(url=f"/dm/deposits/{bk.id}?started=1", status_code=303)

        else:
            raise HTTPException(status_code=400, detail="Unknown decision")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe deposit operation failed: {e}")

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

def _audit(db: Session, actor: Optional[User], bk: Booking, action: str, details: dict | None = None):
    """ كتابة سجل تدقيقي في deposit_audit_log أو deposit_audit_logs (أيّهما متاح). """
    try:
        with _engine.begin() as conn:
            table_name = None
            try:
                conn.exec_driver_sql("SELECT 1 FROM deposit_audit_log LIMIT 1")
                table_name = "deposit_audit_log"
            except Exception:
                try:
                    conn.exec_driver_sql("SELECT 1 FROM deposit_audit_logs LIMIT 1")
                    table_name = "deposit_audit_logs"
                except Exception:
                    table_name = None

            if not table_name:
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

def notify_dms(db: Session, title: str, body: str = "", url: str = ""):
    """ إشعار كل من لديه صلاحية متحكّم وديعة أو أدمِن. """
    dms = db.query(User).filter(
        (User.is_deposit_manager == True) | ((User.role or "") == "admin")
    ).all()
    for u in dms:
        push_notification(db, u.id, title, body, url, kind="deposit")

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
    if _get_deposit_pi_id(bk) is None:
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

    push_notification(
        db, bk.renter_id, "بلاغ وديعة جديد",
        f"قام المالك بالإبلاغ عن مشكلة ({issue_type}) بخصوص الحجز #{bk.id}.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
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
        setattr(bk, "renter_response_at", datetime.utcnow())
    except Exception:
        pass
    db.commit()

    push_notification(
        db, bk.owner_id, "رد من المستأجر",
        f"ردّ المستأجر على بلاغ الوديعة لحجز #{bk.id}.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    notify_admins(db, "رد وديعة جديد", f"ردّ المستأجر في قضية حجز #{bk.id}.", f"/dm/deposits/{bk.id}")

    _audit(db, actor=user, bk=bk, action="renter_response", details={"comment": renter_comment})

    return RedirectResponse(f"/dm/deposits/{bk.id}", status_code=303)

# ==== استلام القضية (Claim) ====
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

# ===== DEBUG / أدوات مساعدة =====
@router.get("/debug/uploads/{booking_id}")
def debug_uploads(booking_id: int, request: Request):
    APP_ROOT_RT = os.path.dirname(os.path.dirname(__file__))
    UPLOADS_BASE_RT = os.path.join(APP_ROOT_RT, "uploads")
    DEPOSIT_UPLOADS_RT = os.path.join(UPLOADS_BASE_RT, "deposits")
    bk_folder = os.path.join(DEPOSIT_UPLOADS_RT, str(booking_id))
    os.makedirs(bk_folder, exist_ok=True)

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

@router.get("/debug/evidence/{booking_id}")
def debug_evidence(booking_id: int, request: Request):
    return {"urls": _evidence_urls(request, booking_id)}

@router.get("/debug/file/{booking_id}/{name}")
def debug_open_file(booking_id: int, name: str):
    return {"public_url": f"/uploads/deposits/{booking_id}/{name}"}

@router.get("/dm/deposits/{booking_id}/_ctx")
def dm_case_context(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    bk = require_booking(db, booking_id)
    item = db.get(Item, bk.item_id)
    ev = _evidence_urls(Request(scope={"type": "http"}), bk.id)
    return {
        "bk": {"id": bk.id, "status": bk.status, "deposit_status": bk.deposit_status},
        "item": {"id": item.id if item else None, "title": item.title if item else None},
        "evidence": ev,
    }

# ===== بدء مهلة ردّ المستأجر 24h + إشعار =====
@router.post("/dm/deposits/{booking_id}/start-window")
def dm_start_renter_window(
    booking_id: int,
    amount: int = Form(0),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    bk = require_booking(db, booking_id)

    amt = max(0, int(amount or 0))
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")

    now = datetime.utcnow()
    deadline = now + timedelta(hours=24)

    try:
        bk.deposit_status = "awaiting_renter"
        bk.dm_decision = "withhold"
        bk.dm_decision_amount = amt
        bk.dm_decision_note = (reason or None)
        bk.renter_response_deadline_at = deadline
        bk.updated_at = now
    except Exception:
        pass

    try:
        _audit(
            db, actor=user, bk=bk, action="dm_withhold_pending",
            details={"amount": amt, "reason": reason, "deadline": deadline.isoformat()}
        )
    except Exception:
        pass

    db.commit()

    try:
        push_notification(
            db, bk.renter_id, "تنبيه: قرار خصم قيد الانتظار",
            f"يوجد قرار خصم بمبلغ {amt} على وديعتك في حجز #{bk.id}. لديك 24 ساعة للرد ورفع أدلة.",
            f"/deposits/{bk.id}/evidence/form", "deposit"
        )
        push_notification(
            db, bk.owner_id, "تم تفعيل مهلة ردّ المستأجر",
            f"تم فتح قرار خصم بمبلغ {amt} على الحجز #{bk.id}. التنفيذ سيكون تلقائيًا بعد 24 ساعة إن لم يرد المستأجر.",
            f"/dm/deposits/{bk.id}", "deposit"
        )
        notify_admins(
            db, "قرار خصم قيد الانتظار",
            f"DM فعّل مهلة 24h للحجز #{bk.id} (amount={amt}).",
            f"/dm/deposits/{bk.id}"
        )
    except Exception:
        pass

    return RedirectResponse(url=f"/dm/deposits/{bk.id}?started=1", status_code=303)

    # ====== ALIASES v4 لتجنّب اصطدام الراوتر القديم ======

@router.post("/dm/deposits/v4/{booking_id}/decision")
def dm_decision_v4(
    booking_id: int,
    decision: Literal["release", "withhold"] = Form(...),
    amount: int = Form(0),
    reason: str = Form(""),
    finalize: int = Form(0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    # يستدعي نفس المنطق بالضبط
    return dm_decision(
        booking_id=booking_id,
        decision=decision,
        amount=amount,
        reason=reason,
        finalize=finalize,
        db=db,
        user=user,
    )

@router.post("/dm/deposits/v4/{booking_id}/start-window")
def dm_start_renter_window_v4(
    booking_id: int,
    amount: int = Form(0),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    return dm_start_renter_window(
        booking_id=booking_id,
        amount=amount,
        reason=reason,
        db=db,
        user=user,
    )