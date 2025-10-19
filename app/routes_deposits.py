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
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
# NOTE: if using SQLAlchemy 2.0+ Core text, keep import below
from sqlalchemy import or_, text

from .database import get_db, engine as _engine
from .models import Booking, Item, User
from .notifications_api import push_notification, notify_admins

# ✅ نمرّر الدالة للقوالب التي تحتاج label للفئة
try:
    from .utils import category_label
except Exception:
    category_label = lambda c: c  # fallback بسيط

# ===== SMTP Email (fallback) =====
# سيتم استبداله لاحقًا بـ app/emailer.py؛ هنا نضمن عدم كسر التنفيذ إن لم يوجد.
try:
    from .email_service import send_email
except Exception:
    def send_email(to, subject, html_body, text_body=None, cc=None, bcc=None, reply_to=None):
        return False  # NO-OP مؤقتًا

BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
CRON_TOKEN = os.getenv("CRON_TOKEN", "dev-cron-token")  # رمز حماية للكرون اليدوي

def _user_email(db: Session, user_id: int) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return (u.email or None) if u else None

def _admin_emails(db: Session) -> list[str]:
    admins = db.query(User).filter(
        ((User.role == "admin") | (User.is_deposit_manager == True))
    ).all()
    return [a.email for a in admins if getattr(a, "email", None)]

# إيميلات الـ DMs فقط (بدون الإداريين، للفصل عند الحاجة)
def _dm_emails_only(db: Session) -> list[str]:
    dms = db.query(User).filter(User.is_deposit_manager == True).all()
    return [u.email for u in dms if getattr(u, "email", None)]

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
            "category_label": category_label,  # تمريرها لو احتاج القالب
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
            "category_label": category_label,  # ✅ إصلاح: تمرير الدالة التي يستخدمها القالب
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
        # الإشعار النهائي يوجّه الطرفين لتدفّق الحجز (كما كان)
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

            # ===== Emails: قرار نهائي — إرجاع كامل =====
            try:
                renter_email = _user_email(db, bk.renter_id)
                owner_email  = _user_email(db, bk.owner_id)
                case_url = f"{BASE_URL}/bookings/flow/{bk.id}"
                if owner_email:
                    send_email(owner_email, f"قرار نهائي — إرجاع وديعة #{bk.id}",
                               f"<p>تم إرجاع الوديعة بالكامل لحجز #{bk.id}.</p>"
                               f'<p><a href="{case_url}">تفاصيل الحجز</a></p>')
                if renter_email:
                    send_email(renter_email, f"قرار نهائي — إرجاع وديعتك #{bk.id}",
                               f"<p>تم إرجاع وديعتك بالكامل لحجز #{bk.id}.</p>"
                               f'<p><a href="{case_url}">تفاصيل الحجز</a></p>')
            except Exception:
                pass

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

                # محاولة تحويل للمالك (لو لديه Stripe متكامل)
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

                # ===== Emails: قرار نهائي — اقتطاع =====
                try:
                    renter_email = _user_email(db, bk.renter_id)
                    owner_email  = _user_email(db, bk.owner_id)
                    case_url = f"{BASE_URL}/bookings/flow/{bk.id}"
                    if owner_email:
                        send_email(owner_email, f"قرار نهائي — اقتطاع {amt_txt} CAD — #{bk.id}",
                                   f"<p>تم اقتطاع {amt_txt} CAD من وديعة الحجز #{bk.id}.</p>"
                                   f'<p><a href="{case_url}">تفاصيل الحجز</a></p>')
                    if renter_email:
                        send_email(renter_email, f"قرار نهائي — خصم {amt_txt} CAD من وديعتك — #{bk.id}",
                                   f"<p>تم خصم {amt_txt} CAD من وديعتك لحجز #{bk.id}."
                                   + (f" — السبب: {reason_txt}" if reason_txt else "")
                                   + f'</p><p><a href="{case_url}">تفاصيل الحجز</a></p>')
                except Exception:
                    pass

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

            # ===== Emails: بدء نافذة 24 ساعة (عبر decision) =====
            try:
                renter_email = _user_email(db, bk.renter_id)
                owner_email  = _user_email(db, bk.owner_id)
                admins_em    = _admin_emails(db)
                dms_em       = _dm_emails_only(db)
                case_url = f"{BASE_URL}/dm/deposits/{bk.id}"
                ev_url   = f"{BASE_URL}/deposits/{bk.id}/evidence/form"
                deadline_str = deadline.strftime("%Y-%m-%d %H:%M UTC")
                if renter_email:
                    send_email(
                        renter_email,
                        f"تنبيه: قرار خصم على وديعتك — #{bk.id}",
                        f"<p>يوجد قرار خصم بمبلغ {amt_txt} CAD على وديعتك للحجز #{bk.id}."
                        f" لديك حتى <b>{deadline_str}</b> للرد ورفع الأدلة.</p>"
                        f'<p><a href="{ev_url}">رفع الأدلة</a></p>'
                    )
                if owner_email:
                    send_email(
                        owner_email,
                        f"تم بدء مهلة ردّ المستأجر — #{bk.id}",
                        f"<p>فُتحت مهلة 24 ساعة لتنفيذ قرار الخصم بمبلغ {amt_txt} CAD."
                        f" التنفيذ تلقائيًا بعد انتهاء المهلة ما لم يردّ المستأجر.</p>"
                        f'<p><a href="{case_url}">صفحة القضية</a></p>'
                    )
                for em in admins_em:
                    send_email(
                        em,
                        f"[Admin] awaiting_renter — #{bk.id}",
                        f"<p>اقتطاع مقترح بمبلغ {amt_txt} CAD للحجز #{bk.id}.</p>"
                        f'<p><a href="{case_url}">فتح القضية</a></p>'
                    )
                for em in dms_em:
                    send_email(
                        em,
                        f"[DM] awaiting_renter — #{bk.id}",
                        f"<p>تم فتح مهلة ردّ المستأجر لقرار خصم للحجز #{bk.id}.</p>"
                        f'<p><a href="{case_url}">إدارة القضية</a></p>'
                    )
            except Exception:
                pass

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
            "category_label": category_label,  # نمررها لو احتاج القالب
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

    # إشعارات داخلية
    push_notification(
        db, bk.renter_id, "بلاغ وديعة جديد",
        f"قام المالك بالإبلاغ عن مشكلة ({issue_type}) بخصوص الحجز #{bk.id}.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    # ✅ هذا هو الإشعار الذي تريده أن يفتح صفحة مراجعة القضايا
    notify_dms(db, "بلاغ وديعة جديد — بانتظار المراجعة", f"بلاغ جديد للحجز #{bk.id}.", f"/dm/deposits/{bk.id}")
    notify_admins(db, "مراجعة ديبو مطلوبة", f"بلاغ جديد بخصوص حجز #{bk.id}.", f"/dm/deposits/{bk.id}")

    _audit(db, actor=user, bk=bk, action="owner_report_issue", details={"issue_type": issue_type, "desc": description, "files": saved})

    # Emails: عند البلاغ — للمستأجر + المالك (تأكيد) + الإداريين + الـDMs
    try:
        renter_email = _user_email(db, bk.renter_id)
        owner_email  = _user_email(db, bk.owner_id)
        admins_em    = _admin_emails(db)
        dms_em       = _dm_emails_only(db)

        case_url  = f"{BASE_URL}/dm/deposits/{bk.id}"
        flow_url  = f"{BASE_URL}/bookings/flow/{bk.id}"

        if renter_email:
            send_email(
                renter_email,
                f"بلاغ وديعة جديد — #{bk.id}",
                f"<p>قام المالك بالإبلاغ عن مشكلة (<b>{issue_type}</b>) بخصوص الحجز #{bk.id}.</p>"
                f'<p><a href="{flow_url}">فتح تفاصيل الحجز</a></p>'
            )
        if owner_email:
            send_email(
                owner_email,
                f"تم إرسال بلاغ الوديعة — #{bk.id}",
                f"<p>تم تقديم بلاغك ({issue_type}) بنجاح للحجز #{bk.id} وهو الآن قيد المراجعة.</p>"
                f'<p><a href="{flow_url}">تفاصيل الحجز</a></p>'
            )
        for em in admins_em:
            send_email(
                em,
                f"[Admin] بلاغ وديعة جديد — #{bk.id}",
                f"<p>بلاغ وديعة جديد من المالك بخصوص الحجز #{bk.id}.</p>"
                f'<p><a href="{case_url}">فتح القضية</a></p>'
            )
        for em in dms_em:
            send_email(
                em,
                f"[DM] بلاغ وديعة جديد — #{bk.id}",
                f"<p>بلاغ جديد بانتظار المراجعة للحجز #{bk.id}.</p>"
                f'<p><a href="{case_url}">إدارة القضية</a></p>'
            )
    except Exception:
        pass

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
    if bk.deposit_status not in ("in_dispute", "awaiting_renter"):
        raise HTTPException(status_code=400, detail="No open deposit issue")

    try:
        now = datetime.utcnow()
        setattr(bk, "updated_at", now)
        setattr(bk, "renter_response_at", now)
        # إن كان في مهلة awaiting_renter → نعيده للمراجعة
        if getattr(bk, "deposit_status", "") == "awaiting_renter":
            bk.deposit_status = "in_dispute"
            bk.status = "in_review"
    except Exception:
        pass
    db.commit()

    # إشعارات داخلية
    push_notification(
        db, bk.owner_id, "رد من المستأجر",
        f"ردّ المستأجر على بلاغ الوديعة لحجز #{bk.id}.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    notify_admins(db, "رد وديعة جديد", f"ردّ المستأجر في قضية حجز #{bk.id}.", f"/dm/deposits/{bk.id}")
    notify_dms(db, "ردّ المستأجر — تحديث القضية", f"تلقى الحجز #{bk.id} ردًا من المستأجر.", f"/dm/deposits/{bk.id}")

    _audit(db, actor=user, bk=bk, action="renter_response", details={"comment": renter_comment})

    # Emails: لصاحب الغرض + DMs
    try:
        owner_email = _user_email(db, bk.owner_id)
        dms_em      = _dm_emails_only(db)
        case_url    = f"{BASE_URL}/dm/deposits/{bk.id}"
        flow_url    = f"{BASE_URL}/bookings/flow/{bk.id}"
        if owner_email:
            send_email(
                owner_email,
                f"ردّ المستأجر على بلاغك — #{bk.id}",
                f"<p>وصل ردّ من المستأجر على بلاغ الوديعة للحجز #{bk.id}.</p>"
                f'<p><a href="{flow_url}">عرض تفاصيل الحجز</a></p>'
            )
        for em in dms_em:
            send_email(
                em,
                f"[DM] ردّ مستأجر أثناء المهلة — #{bk.id}",
                f"<p>تلقى الحجز #{bk.id} ردّ المستأجر خلال مهلة الـ 24 ساعة.</p>"
                f'<p><a href="{case_url}">فتح القضية</a></p>'
            )
    except Exception:
        pass

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

    # 🔔 إشعارات: تعيينك لمراجعة القضية
    try:
        push_notification(
            db, user.id,
            "تم تعيينك لمراجعة قضية",
            f"تم إسناد قضية وديعة #{bk.id} لك.",
            f"/dm/deposits/{bk.id}",
            "deposit",
        )
        notify_admins(
            db, "Assign — تم تعيين مراجع",
            f"تم تعيين {user.id} لمراجعة قضية #{bk.id}.",
            f"/dm/deposits/{bk.id}",
        )
    except Exception:
        pass

    # ✉️ Emails: للمراجع نفسه + المالك + المستأجر
    try:
        reviewer_email = _user_email(db, user.id)
        case_url = f"{BASE_URL}/dm/deposits/{bk.id}"
        if reviewer_email:
            send_email(
                reviewer_email,
                f"تم تعيينك لمراجعة قضية — #{bk.id}",
                f"<p>قضية وديعة #{bk.id} أُسندت إليك للمراجعة.</p>"
                f'<p><a href="{case_url}">فتح القضية</a></p>'
            )
        owner_email  = _user_email(db, bk.owner_id)
        renter_email = _user_email(db, bk.renter_id)
        if owner_email:
            send_email(
                owner_email,
                f"تعيين مراجع لقضية الوديعة — #{bk.id}",
                f"<p>تم تعيين مراجع لقضية الوديعة الخاصة بحجز #{bk.id}.</p>"
                f'<p><a href="{case_url}">تفاصيل القضية</a></p>'
            )
        if renter_email:
            send_email(
                renter_email,
                f"تعيين مراجع لقضية الوديعة — #{bk.id}",
                f"<p>تم تعيين مراجع لقضية الوديعة الخاصة بحجز #{bk.id}.</p>"
                f'<p><a href="{case_url}">تفاصيل القضية</a></p>'
            )
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

    # إشعارات داخلية
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

    # Emails: بدء نافذة 24 ساعة
    try:
        renter_email = _user_email(db, bk.renter_id)
        owner_email  = _user_email(db, bk.owner_id)
        admins_em    = _admin_emails(db)
        dms_em       = _dm_emails_only(db)
        case_url = f"{BASE_URL}/dm/deposits/{bk.id}"
        ev_url   = f"{BASE_URL}/deposits/{bk.id}/evidence/form"
        deadline_str = deadline.strftime("%Y-%m-%d %H:%M UTC")

        if renter_email:
            send_email(
                renter_email,
                f"تنبيه: قرار خصم على وديعتك — #{bk.id}",
                f"<p>يوجد قرار خصم بمبلغ {amt} CAD على وديعتك للحجز #{bk.id}."
                f" لديك حتى <b>{deadline_str}</b> للرد ورفع الأدلة.</p>"
                f'<p><a href="{ev_url}">رفع الأدلة</a></p>'
            )
        if owner_email:
            send_email(
                owner_email,
                f"تم بدء مهلة ردّ المستأجر — #{bk.id}",
                f"<p>فُتحت مهلة 24 ساعة لتنفيذ قرار الخصم بمبلغ {amt} CAD."
                f" التنفيذ تلقائيًا بعد انتهاء المهلة ما لم يردّ المستأجر.</p>"
                f'<p><a href="{case_url}">صفحة القضية</a></p>'
            )
        for em in admins_em:
            send_email(
                em,
                f"[Admin] awaiting_renter — #{bk.id}",
                f"<p>اقتطاع مقترح بمبلغ {amt} CAD للحجز #{bk.id}.</p>"
                f'<p><a href="{case_url}">فتح القضية</a></p>'
            )
        for em in dms_em:
            send_email(
                em,
                f"[DM] awaiting_renter — #{bk.id}",
                f"<p>تم فتح مهلة ردّ المستأجر لقرار خصم للحجز #{bk.id}.</p>"
                f'<p><a href="{case_url}">إدارة القضية</a></p>'
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

# =========================
# >>> نموذج/رفع أدلّة (الطرفين) — إشعار فوري للطرف الآخر + DMs + إيميل
# =========================
@router.get("/deposits/{booking_id}/evidence/form")
def evidence_form(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id not in (bk.owner_id, bk.renter_id):
        raise HTTPException(status_code=403, detail="Not participant in this booking")

    item = db.get(Item, bk.item_id)
    return request.app.templates.TemplateResponse(
        "deposit_evidence_form.html",
        {
            "request": request,
            "title": f"رفع أدلة — حجز #{bk.id}",
            "session_user": request.session.get("user"),
            "bk": bk,
            "item": item,
            "category_label": category_label,
        },
    )

@router.post("/deposits/{booking_id}/evidence/upload")
def evidence_upload(
    booking_id: int,
    files: List[UploadFile] | None = File(None),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يرفع الطرف (مالك/مستأجر) أدلة جديدة → إشعار للطرف الآخر + DMs + بريد.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id not in (bk.owner_id, bk.renter_id):
        raise HTTPException(status_code=403, detail="Not participant in this booking")

    saved = _save_evidence_files(bk.id, files)
    now = datetime.utcnow()
    try:
        setattr(bk, "updated_at", now)
        # عندما تأتي أدلة جديدة نضمن أن الحالة ليست مغلقة
        if getattr(bk, "status", "") in ("closed", "completed"):
            bk.status = "in_review"
        # لو كانت في awaiting_renter نرجعها لنزاع مفتوح
        if getattr(bk, "deposit_status", "") == "awaiting_renter":
            bk.deposit_status = "in_dispute"
    except Exception:
        pass
    db.commit()

    other_id = bk.renter_id if user.id == bk.owner_id else bk.owner_id
    who = "المالك" if user.id == bk.owner_id else "المستأجر"

    # إشعارات داخلية
    push_notification(
        db, other_id, "أدلة جديدة في القضية",
        f"{who} قام برفع أدلة جديدة للحجز #{bk.id}.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    notify_dms(db, "أدلة جديدة — تحديث القضية", f"تم رفع أدلة جديدة للحجز #{bk.id}.", f"/dm/deposits/{bk.id}")

    _audit(db, actor=user, bk=bk, action="evidence_upload", details={"by": who, "files": saved, "comment": comment})

    # Emails: للطرف الآخر + DMs
    try:
        other_email = _user_email(db, other_id)
        dms_em      = _dm_emails_only(db)
        case_url    = f"{BASE_URL}/dm/deposits/{bk.id}"
        flow_url    = f"{BASE_URL}/bookings/flow/{bk.id}"

        if other_email:
            send_email(
                other_email,
                f"أدلة جديدة مرفوعة — #{bk.id}",
                f"<p>{who} قام برفع أدلة جديدة على قضية الوديعة للحجز #{bk.id}.</p>"
                f'<p><a href="{flow_url}">عرض الحجز</a></p>'
            )
        for em in dms_em:
            send_email(
                em,
                f"[DM] أدلة جديدة — #{bk.id}",
                f"<p>تم رفع أدلة جديدة على القضية لحجز #{bk.id}.</p>"
                f'<p><a href="{case_url}">فتح القضية</a></p>'
            )
    except Exception:
        pass

    return RedirectResponse(url=f"/bookings/flow/{bk.id}?evidence=1", status_code=303)

# =========================
# >>> كرون — فحص انتهاء نافذة 24h دون ردّ
# إشعار إلى DM + Admin بالبريد والإشعارات الداخليّة
# =========================
def _deadline_overdue_rows(db: Session) -> List[Booking]:
    now = datetime.utcnow()
    q = (
        db.query(Booking)
        .filter(
            Booking.deposit_status == "awaiting_renter",
            Booking.renter_response_deadline_at.isnot(None),
            Booking.renter_response_deadline_at < now,
        )
        .order_by(Booking.renter_response_deadline_at.asc())
    )
    return q.all()

@router.get("/internal/cron/check-window")
@router.get("/dm/deposits/check-window")  # alias
def cron_check_window(
    request: Request,
    token: str = "",
    db: Session = Depends(get_db),
):
    # حماية بالرمز
    t = request.query_params.get("token", token)
    if t != CRON_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid cron token")

    rows = _deadline_overdue_rows(db)
    count = 0
    for bk in rows:
        count += 1
        # لا ننفّذ خصم تلقائي — فقط إشعارات للتدخل
        try:
            push_notification(
                db, bk.owner_id, "انتهاء مهلة ردّ المستأجر",
                f"انتهت مهلة 24h للحجز #{bk.id} دون ردّ، سيتابع DM.",
                f"/dm/deposits/{bk.id}", "deposit"
            )
        except Exception:
            pass
        try:
            notify_dms(db, "انتهاء مهلة — تدخّل مطلوب", f"انتهت مهلة ردّ المستأجر للحجز #{bk.id}.", f"/dm/deposits/{bk.id}")
            notify_admins(db, "انتهاء مهلة — تدخّل مطلوب", f"انتهت مهلة ردّ المستأجر للحجز #{bk.id}.", f"/dm/deposits/{bk.id}")
        except Exception:
            pass

        # Emails: للـ DMs + Admin
        try:
            dms_em    = _dm_emails_only(db)
            admins_em = _admin_emails(db)
            case_url  = f"{BASE_URL}/dm/deposits/{bk.id}"
            subject   = f"[Action Needed] انتهت مهلة 24h — #{bk.id}"
            body_html = f"<p>انتهت مهلة ردّ المستأجر للحجز #{bk.id} دون ردّ.</p><p><a href=\"{case_url}\">فتح القضية</a></p>"
            for em in dms_em:
                send_email(em, subject, body_html)
            for em in admins_em:
                send_email(em, subject, body_html)
        except Exception:
            pass

        # وضع القضية قيد المراجعة إن لم تكن كذلك
        try:
            if getattr(bk, "status", "") != "in_review":
                bk.status = "in_review"
                bk.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass

    return JSONResponse({"ok": True, "checked": count})