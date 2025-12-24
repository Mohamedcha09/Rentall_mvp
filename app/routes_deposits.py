# app/routes_deposits.py
from __future__ import annotations
from typing import Optional, Literal, List, Dict, Annotated
from datetime import datetime, timedelta
import os
import shutil
import stripe
import mimetypes
from fastapi import BackgroundTasks

# --- NEW: Cloudinary ---
import cloudinary
import cloudinary.uploader

from fastapi import (
    APIRouter,
    Depends,
    Request,
    HTTPException,
    Form,
    UploadFile,
    File
)
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, text

from .database import get_db, engine as _engine
from .models import Booking, Item, User
from .notifications_api import push_notification, notify_admins


try:
    from .models import DepositEvidence
except Exception:
    DepositEvidence = None

# ✅ pass category label to templates
try:
    from .utils import category_label
except Exception:
    category_label = lambda c: c

# ===== Email fallback =====
try:
    from .email_service import send_email
except Exception:
    def send_email(to, subject, html_body, text_body=None, cc=None, bcc=None, reply_to=None):
        return False

# ===== notify_dms fallback =====
try:
    from .notifications_api import notify_dms
except Exception:
    def notify_dms(db, title, body, url=None):
        try:
            dms = db.query(User).filter(User.is_deposit_manager == True).all()
            for u in dms:
                try:
                    push_notification(
                        db, u.id,
                        title or "Alert — Deposit",
                        body or "",
                        url or "/dm/deposits",
                        "deposit"
                    )
                except Exception:
                    pass
            try:
                notify_admins(db, title or "Alert — Deposit", body or "", url or "/dm/deposits")
            except Exception:
                pass
        except Exception:
            pass
        return True

# ===== audit fallback =====
try:
    from .audit import audit_action as _audit
except Exception:
    def _audit(db, actor, bk, action, details=None):
        return None

# ===== helpers email list fallbacks (avoid NameError) =====
def _user_email(db: Session, user_id: int) -> Optional[str]:
    try:
        u = db.get(User, user_id) if user_id else None
        return (u.email or None) if u else None
    except Exception:
        return None

def _admin_emails(db: Session) -> List[str]:
    try:
        rows = db.query(User).filter(((User.role == "admin") | (User.is_deposit_manager == True))).all()
        return [getattr(r, "email", None) for r in rows if getattr(r, "email", None)]
    except Exception:
        return []

def _dm_emails_only(db: Session) -> List[str]:
    try:
        rows = db.query(User).filter(User.is_deposit_manager == True).all()
        return [getattr(r, "email", None) for r in rows if getattr(r, "email", None)]
    except Exception:
        return []

BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
CRON_TOKEN = os.getenv("CRON_TOKEN", "dev-cron-token")

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

# ============ Evidence (files) paths ============
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOADS_BASE = os.path.join(APP_ROOT, "uploads")
DEPOSIT_UPLOADS = os.path.join(UPLOADS_BASE, "deposits")
os.makedirs(DEPOSIT_UPLOADS, exist_ok=True)

ALLOWED_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp4", ".mov", ".m4v", ".avi", ".wmv",
    ".heic", ".heif", ".bmp", ".tiff",
}

def _final_summary_url(bk_id: int) -> str:
    return f"/bookings/{bk_id}/deposit/summary"

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

# >>> Local save + Cloudinary upload [(local_name, secure_url)]
def _save_evidence_files_and_cloud(booking_id: int, files: List[UploadFile] | None) -> List[tuple[str, str]]:
    saved_names = _save_evidence_files(booking_id, files)
    results: List[tuple[str, str]] = []
    folder = _booking_folder(booking_id)
    for name in saved_names:
        url = f"/uploads/deposits/{booking_id}/{name}"
        try:
            full_path = os.path.join(folder, name)
            up = cloudinary.uploader.upload(
                full_path,
                folder=f"deposits/{booking_id}",
                public_id=os.path.splitext(name)[0],
                resource_type="auto"
            )
            url = up.get("secure_url") or url
        except Exception:
            pass
        results.append((name, url))
    return results
# <<<

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

# ============ General Helpers ============
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

# NEW: helper — tag description safely with a phase marker
def _tagged_desc(phase: str, txt: str | None) -> str:
    phase = (phase or "").strip().lower()
    base = txt or ""
    if phase in ("pickup", "return"):
        return f"[{phase}_renter] {base}".strip()
    return base.strip()

def _is_closed(bk: Booking) -> bool:
    ds = (getattr(bk, "deposit_status", "") or "").lower()
    st = (getattr(bk, "status", "") or "").lower()
    return (st == "closed") or (ds in {"refunded", "partially_withheld", "no_deposit"})

# ====== Read/Write PI id ======
def _get_deposit_pi_id(bk: Booking) -> Optional[str]:
    return (
        getattr(bk, "deposit_hold_intent_id", None)
        or getattr(bk, "deposit_hold_id", None)
    )

def _set_deposit_pi_id(bk: Booking, pi_id: Optional[str]) -> None:
    try:
        setattr(bk, "deposit_hold_intent_id", pi_id)
    except Exception:
        pass
    try:
        setattr(bk, "deposit_hold_id", pi_id)
    except Exception:
        pass

def _has_renter_reply(db: Session, booking_id: int, bk: Booking | None = None) -> bool:
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

# --- NEW: split renter evidences by phase tag ---
def _split_renter_evidence(bk):
    try:
        evs = list(getattr(bk, "deposit_evidences", []) or [])
    except Exception:
        evs = []
    renters = [e for e in evs if (getattr(e, "side", "") or "").lower() == "renter"]
    pickup, ret, other = [], [], []
    for e in renters:
        desc = (getattr(e, "description", "") or "").strip().lower()
        if desc.startswith("[pickup_renter]"):
            pickup.append(e)
        elif desc.startswith("[return_renter]"):
            ret.append(e)
        else:
            other.append(e)
    return pickup, ret, other

@router.get("/dm/deposits")
def dm_queue(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    state: Literal["all", "new", "awaiting_renter", "awaiting_dm", "closed"] = "all",
    q: Optional[str] = None,
):
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    # ===============================
    # BASE FILTERS (REAL COLUMNS ONLY)
    # ===============================
    base_filters = [
        or_(
            Booking.hold_deposit_amount > 0,
            Booking.deposit_audits.any(),   # 👈 بديل deposit_status
            Booking.status.in_(["returned", "in_review", "closed"]),
        )
    ]

    # ===============================
    # STATE FILTER
    # ===============================
    if state == "closed":
        base_filters.append(Booking.status == "closed")

    elif state in ("new", "awaiting_dm"):
        # حالات فيها بلاغ / مراجعة
        base_filters.append(Booking.deposit_audits.any())

        if hasattr(Booking, "dm_assignee_id"):
            base_filters.append(
                or_(
                    Booking.dm_assignee_id.is_(None),
                    Booking.dm_assignee_id == 0,
                )
            )

    # ===============================
    # QUERY
    # ===============================
    qset = db.query(Booking).filter(and_(*base_filters))

    # ===============================
    # SEARCH
    # ===============================
    if q:
        q = q.strip()

        if q.startswith("#") and q[1:].isdigit():
            qset = qset.filter(Booking.id == int(q[1:]))

        elif q.isdigit():
            qset = qset.filter(Booking.id == int(q))

        else:
            qset = qset.join(Item, Item.id == Booking.item_id, isouter=True)
            like = f"%{q}%"
            qset = qset.filter(Item.title.ilike(like))

    # ===============================
    # ORDER
    # ===============================
    order_col = (
        Booking.updated_at.desc()
        if hasattr(Booking, "updated_at")
        else Booking.id.desc()
    )

    cases = qset.order_by(order_col).all()

    # ===============================
    # PREFETCH ITEMS
    # ===============================
    item_ids = {b.item_id for b in cases}
    items = (
        db.query(Item).filter(Item.id.in_(item_ids)).all()
        if item_ids
        else []
    )
    items_map = {it.id: it for it in items}

    return request.app.templates.TemplateResponse(
        "dm_queue.html",
        {
            "request": request,
            "title": "Deposit Cases",
            "session_user": request.session.get("user"),
            "cases": cases,
            "items_map": items_map,
            "category_label": category_label,
            "state": state,
            "q": q or "",
        },
    )

# ============ Case page ============
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
    renter_pickup, renter_return, renter_other = _split_renter_evidence(bk)

    evidence_urls = [str(u) for u in _evidence_urls(request, bk.id) if u]
    has_renter_reply = _has_renter_reply(db, bk.id, bk)

    resp = request.app.templates.TemplateResponse(
        "dm_case.html",
        {
            "request": request,
            "title": f"Deposit Case #{bk.id}",
            "session_user": request.session.get("user"),
            "bk": bk,
            "booking": bk,
            "item": item,
            "evidence": evidence_urls,
            "ev_list": evidence_urls,
            "has_renter_reply": has_renter_reply,
            "category_label": category_label,
            "is_closed": _is_closed(bk),
            "renter_pickup": renter_pickup,
            "renter_return": renter_return,
            "renter_other": renter_other,
        },
    )
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-Route-Version"] = "deposits-v4"
    return resp

# ============ Decision execution (final/pending) ============
@router.post("/dm/deposits/{booking_id}/decision")
def dm_decision(
    booking_id: int,
    decision: Literal["release", "withhold"] = Form(...),
    amount: int = Form(0),
    reason: str = Form(""),
    finalize: int = Form(0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Access denied")

    bk = require_booking(db, booking_id)
    if _is_closed(bk):
        raise HTTPException(status_code=400, detail="case already closed")

    pi_id = _get_deposit_pi_id(bk)
    now = datetime.utcnow()

    def _notify_final(title_owner: str, body_owner: str, title_renter: str, body_renter: str):
        final_url = _final_summary_url(bk.id)  # ==> "/bookings/{id}/deposit/summary"
        push_notification(db, bk.owner_id,  title_owner,  body_owner,  final_url, "deposit")
        push_notification(db, bk.renter_id, title_renter, body_renter, final_url, "deposit")
        # Admin keeps DM page open
        notify_admins(db, "Final Decision Notice", f"Booking #{bk.id} — {decision}", f"/dm/deposits/{bk.id}")

    try:
        if decision == "release":
            if pi_id:
                try:
                    stripe.PaymentIntent.cancel(pi_id)
                except Exception:
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
                "Final Decision Announced", f"The deposit for booking #{bk.id} has been fully refunded.",
                "Final Decision Announced", f"Your deposit has been fully refunded for booking #{bk.id}."
            )

            try:
                renter_email = _user_email(db, bk.renter_id)
                owner_email  = _user_email(db, bk.owner_id)
                case_url = f"{BASE_URL}{_final_summary_url(bk.id)}"  # BASE_URL + "/bookings/{id}/deposit/summary"
                if owner_email:
                    send_email(
                        owner_email,
                        f"Final Decision — Deposit Refund #{bk.id}",
                        f"<p>The deposit was fully refunded for booking #{bk.id}.</p>"
                        f'<p><a href="{case_url}">Final decision details</a></p>'
                    )
                if renter_email:
                    send_email(
                        renter_email,
                        f"Final Decision — Your Deposit Refund #{bk.id}",
                        f"<p>Your deposit was fully refunded for booking #{bk.id}.</p>"
                        f'<p><a href="{case_url}">Final decision details</a></p>'
                    )
            except Exception:
                pass

            return RedirectResponse(url=_final_summary_url(bk.id), status_code=303)

        elif decision == "withhold":
            amt = max(0, int(amount or 0))

            if finalize:
                if amt <= 0:
                    raise HTTPException(status_code=400, detail="Invalid amount")

                captured_ok = False
                charge_id: Optional[str] = None

                if pi_id:
                    try:
                        pi = stripe.PaymentIntent.capture(pi_id, amount_to_capture=amt * 100)
                        captured_ok = bool(pi and pi.get("status") in ("succeeded", "requires_capture") or True)
                        charge_id = (pi.get("latest_charge") or
                                     ((pi.get("charges") or {}).get("data") or [{}])[0].get("id"))
                    except Exception:
                        captured_ok = False

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

                amt_txt = _fmt_money(amt)
                reason_txt = _short_reason(reason)
                if captured_ok:
                    _notify_final(
                        "Final Decision Announced",
                        f"{amt_txt} CAD was deducted from the deposit in booking #{bk.id}" + (f" — reason: {reason_txt}" if reason_txt else ""),
                        "Final Decision Announced",
                        f"{amt_txt} CAD was deducted from your deposit in booking #{bk.id}" + (f" — reason: {reason_txt}" if reason_txt else "")
                    )
                else:
                    _notify_final(
                        "Final Decision Announced",
                        f"Withholding {amt_txt} CAD for booking #{bk.id} confirmed (no held deposit available to charge).",
                        "Final Decision Announced",
                        f"Withholding {amt_txt} CAD from your deposit for booking #{bk.id} confirmed, but there is no held deposit."
                    )

                try:
                    renter_email = _user_email(db, bk.renter_id)
                    owner_email  = _user_email(db, bk.owner_id)
                    case_url = f"{BASE_URL}{_final_summary_url(bk.id)}"
                    if owner_email:
                        send_email(
                            owner_email,
                            f"Final Decision — Withheld {amt_txt} CAD — #{bk.id}",
                            f"<p>{amt_txt} CAD was withheld from the deposit for booking #{bk.id}.</p>"
                            f'<p><a href="{case_url}">Final decision details</a></p>'
                        )
                    if renter_email:
                        send_email(
                            renter_email,
                            f"Final Decision — {amt_txt} CAD withheld from your deposit — #{bk.id}",
                            f"<p>{amt_txt} CAD was withheld from your deposit for booking #{bk.id}"
                            + (f" — reason: {reason_txt}" if reason_txt else "")
                            + f'</p><p><a href="{case_url}">Final decision details</a></p>'
                        )
                except Exception:
                    pass

                return RedirectResponse(url=_final_summary_url(bk.id), status_code=303)

            # 24h window (not final)
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
                db, bk.owner_id, "Pending Deduction Decision",
                (f"A deduction decision of {amt_txt} CAD was opened for booking #{bk.id}"
                 + (f" — reason: {reason_txt}" if reason_txt else "")
                 + ". It will be executed automatically after 24 hours unless the renter responds."),
                f"/dm/deposits/{bk.id}", "deposit"
            )
            push_notification(
                db, bk.renter_id, "Alert: Deduction Decision on Your Deposit",
                (f"There is a deduction decision of {amt_txt} CAD on your deposit for booking #{bk.id}"
                 + (f" — reason: {reason_txt}" if reason_txt else "")
                 + ". You have 24 hours to respond and upload evidence."),
                f"/deposits/{bk.id}/evidence/form", "deposit"
            )
            notify_admins(db, "Pending Deduction Decision",
                          f"Proposed deduction {amt_txt} CAD — booking #{bk.id}.", f"/dm/deposits/{bk.id}")

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
                        f"Alert: Deduction Decision on Your Deposit — #{bk.id}",
                        f"<p>There is a deduction decision of <b>{amt_txt} CAD</b> on your deposit for booking #{bk.id}."
                        f" You have until <b>{deadline_str}</b> to respond and upload evidence.</p>"
                        f'<p><a href="{ev_url}">Upload Evidence</a></p>'
                    )
                if owner_email:
                    send_email(
                        owner_email,
                        f"Renter Response Window Started — #{bk.id}",
                        f"<p>A 24-hour window has been opened to execute a deduction decision of {amt_txt} CAD."
                        f" It will be executed automatically after the window ends unless the renter responds.</p>"
                        f'<p><a href="{case_url}">Case Page</a></p>'
                    )
                for em in admins_em:
                    send_email(
                        em,
                        f"[Admin] awaiting_renter — #{bk.id}",
                        f"<p>Proposed deduction of {amt_txt} CAD for booking #{bk.id}.</p>"
                        f'<p><a href="{case_url}">Open Case</a></p>'
                    )
                for em in dms_em:
                    send_email(
                        em,
                        f"[DM] awaiting_renter — #{bk.id}",
                        f"<p>The renter response window for a deduction decision has been opened for booking #{bk.id}.</p>"
                        f'<p><a href="{case_url}">Manage Case</a></p>'
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

# ===================== Deposit report =====================
@router.get("/deposits/{booking_id}/report")
def report_deposit_issue_page(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    # Only owner opens the report form, DM/Admin get redirected to the case page
    if user.id != bk.owner_id:
        if can_manage_deposits(user):
            return RedirectResponse(url=f"/dm/deposits/{bk.id}", status_code=303)
        return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

    item = db.get(Item, bk.item_id)

    return request.app.templates.TemplateResponse(
        "deposit_report.html",
        {
            "request": request,
            "title": f"Open Deposit Report — Booking #{bk.id}",
            "session_user": request.session.get("user"),
            "bk": bk,
            "booking": bk,
            "item": item,
            "category_label": category_label,
        },
    )

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
    # --- improved alternative ---
    pi_id = _get_deposit_pi_id(bk)

    # ---- from here to the end of the function must remain inside the function (indented by 4 spaces) ----
    if not pi_id:
        if (bk.payment_method or "").lower() not in ("cash", "manual") and (bk.hold_deposit_amount or 0) <= 0:
            raise HTTPException(status_code=400, detail="No deposit hold found")

    saved_pairs = _save_evidence_files_and_cloud(bk.id, files)

    try:
        from .models import DepositEvidence
        for name, url in saved_pairs:
            db.add(DepositEvidence(
                booking_id=bk.id,
                uploader_id=user.id,
                side="owner",
                kind="image",
                file_path=url,
                description=(description or None),
            ))
        try:
            bk.owner_report_type = (issue_type or None)
            bk.owner_report_reason = (description or None)
            bk.dispute_opened_at = datetime.utcnow()
        except Exception:
            pass
        db.commit()
    except Exception:
        db.rollback()
        pass

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
        db, bk.renter_id, "New Deposit Report",
        f"The owner reported an issue ({issue_type}) for booking #{bk.id}.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    notify_dms(db, "New Deposit Report — Pending Review",
               f"New report for booking #{bk.id}.", "/dm/deposits")
    notify_admins(db, "Deposit Review Required",
                  f"New deposit report for booking #{bk.id}.", "/dm/deposits")

    _audit(db, actor=user, bk=bk, action="owner_report_issue",
           details={"issue_type": issue_type, "desc": description, "files": [p[0] for p in saved_pairs]})

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
                f"New Deposit Report — #{bk.id}",
                f"<p>The owner reported an issue (<b>{issue_type}</b>) regarding booking #{bk.id}.</p>"
                f'<p><a href="{flow_url}">Open booking details</a></p>'
            )
        if owner_email:
            send_email(
                owner_email,
                f"Deposit Report Submitted — #{bk.id}",
                f"<p>Your report ({issue_type}) for booking #{bk.id} was submitted successfully and is now under review.</p>"
                f'<p><a href="{flow_url}">Booking details</a></p>'
            )
        for em in admins_em:
            send_email(em, f"[Admin] New Deposit Report — #{bk.id}",
                       f"<p>New deposit report from the owner for booking #{bk.id}.</p>"
                       f'<p><a href="{case_url}">Open case</a></p>')
        for em in dms_em:
            send_email(em, f"[DM] New Deposit Report — #{bk.id}",
                       f"<p>New report pending review for booking #{bk.id}.</p>"
                       f'<p><a href="{case_url}">Manage case</a></p>')
    except Exception:
        pass

    return request.app.templates.TemplateResponse(
        "deposit_report_ok.html",
        {
            "request": request,
            "title": "Report Submitted",
            "session_user": request.session.get("user"),
            "bk": bk,
        },
        status_code=200
    )

# ========================= Evidence for both parties =========================
@router.post("/deposits/{booking_id}/evidence/upload")
def evidence_upload(
    booking_id: int,
    files: List[UploadFile] | None = File(None),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if _is_closed(bk):
        raise HTTPException(status_code=400, detail="case already closed")
    if user.id not in (bk.owner_id, bk.renter_id):
        raise HTTPException(status_code=403, detail="Not participant in this booking")

    saved_pairs = _save_evidence_files_and_cloud(bk.id, files)

    try:
        from .models import DepositEvidence
        side_val = "owner" if user.id == bk.owner_id else "renter"
        for name, url in saved_pairs:
            db.add(DepositEvidence(
                booking_id=bk.id,
                uploader_id=user.id,
                side=side_val,
                kind="image",
                file_path=url,
                description=(comment or None),
            ))
        db.commit()
    except Exception:
        db.rollback()
        pass

    now = datetime.utcnow()
    try:
        setattr(bk, "updated_at", now)
        if getattr(bk, "status", "") in ("closed", "completed"):
            bk.status = "in_review"
        if getattr(bk, "deposit_status", "") == "awaiting_renter":
            bk.deposit_status = "in_dispute"
        if user.id == bk.renter_id:
            setattr(bk, "renter_response_at", now)
        db.commit()
    except Exception:
        db.rollback()
        pass

    other_id = bk.renter_id if user.id == bk.owner_id else bk.owner_id
    who = "Owner" if user.id == bk.owner_id else "Renter"

    try:
        push_notification(db, other_id, "New Evidence in Case",
                          f"{who} uploaded new evidence for booking #{bk.id}.",
                          f"/bookings/flow/{bk.id}", "deposit")
        notify_dms(db, "New Evidence — Case Updated",
                   f"New evidence uploaded for booking #{bk.id}.", f"/dm/deposits/{bk.id}")
        _audit(db, actor=user, bk=bk, action="evidence_upload",
               details={"by": who, "files": [p[0] for p in saved_pairs], "comment": comment})
    except Exception:
        pass

    try:
        other_email = _user_email(db, other_id)
        dms_em      = _dm_emails_only(db)
        case_url    = f"{BASE_URL}/dm/deposits/{bk.id}"
        flow_url    = f"{BASE_URL}/bookings/flow/{bk.id}"
        if other_email:
            send_email(
                other_email,
                f"New Evidence Uploaded — #{bk.id}",
                f"<p>{who} uploaded new evidence for the deposit case on booking #{bk.id}.</p>"
                f'<p><a href="{flow_url}">View booking</a></p>'
            )
        for em in dms_em:
            send_email(
                em,
                f"[DM] New Evidence — #{bk.id}",
                f"<p>New evidence has been uploaded for the case for booking #{bk.id}.</p>"
                f'<p><a href="{case_url}">Open case</a></p>'
            )
    except Exception:
        pass

    return RedirectResponse(url=f"/bookings/flow/{bk.id}?evidence=1", status_code=303)

# ==== Renter reply ====
@router.post("/deposits/{booking_id}/renter-response")
def renter_response_to_issue(
    booking_id: int,
    renter_comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if _is_closed(bk):
        raise HTTPException(status_code=400, detail="case already closed")
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can respond")
    if bk.deposit_status not in ("in_dispute", "awaiting_renter"):
        raise HTTPException(status_code=400, detail="No open deposit issue")

    try:
        now = datetime.utcnow()
        setattr(bk, "updated_at", now)
        setattr(bk, "renter_response_at", now)
        if getattr(bk, "deposit_status", "") == "awaiting_renter":
            bk.deposit_status = "in_dispute"
            bk.status = "in_review"
    except Exception:
        pass
    db.commit()

    push_notification(
        db, bk.owner_id, "Renter Responded",
        f"The renter responded to the deposit report for booking #{bk.id}.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    notify_admins(db, "New Deposit Reply", f"Renter replied in case for booking #{bk.id}.", f"/dm/deposits/{bk.id}")
    notify_dms(db, "Renter Reply — Case Updated", f"Booking #{bk.id} received a renter reply.", f"/dm/deposits/{bk.id}")

    _audit(db, actor=user, bk=bk, action="renter_response", details={"comment": renter_comment})

    try:
        owner_email = _user_email(db, bk.owner_id)
        dms_em      = _dm_emails_only(db)
        case_url    = f"{BASE_URL}/dm/deposits/{bk.id}"
        flow_url    = f"{BASE_URL}/bookings/flow/{bk.id}"
        if owner_email:
            send_email(
                owner_email,
                f"Renter responded to your report — #{bk.id}",
                f"<p>A renter response was received on the deposit report for booking #{bk.id}.</p>"
                f'<p><a href="{flow_url}">View booking details</a></p>'
            )
        for em in dms_em:
            send_email(
                em,
                f"[DM] Renter reply during window — #{bk.id}",
                f"<p>Booking #{bk.id} received a renter reply during the 24-hour window.</p>"
                f'<p><a href="{case_url}">Open case</a></p>'
            )
    except Exception:
        pass

    return RedirectResponse(f"/dm/deposits/{bk.id}", status_code=303)

# ==== Claim case (DM) ====
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

    try:
        push_notification(
            db, user.id,
            "You have been assigned to review a case",
            f"Deposit case #{bk.id} was assigned to you.",
            f"/dm/deposits/{bk.id}",
            "deposit",
        )
        notify_admins(
            db, "Assign — Reviewer Assigned",
            f"{user.id} was assigned to review case #{bk.id}.",
            f"/dm/deposits/{bk.id}",
        )
    except Exception:
        pass

    try:
        reviewer_email = _user_email(db, user.id)
        case_url = f"{BASE_URL}/dm/deposits/{bk.id}"
        if reviewer_email:
            send_email(
                reviewer_email,
                f"You have been assigned to review a case — #{bk.id}",
                f"<p>Deposit case #{bk.id} has been assigned to you for review.</p>"
                f'<p><a href="{case_url}">Open case</a></p>'
            )
        owner_email  = _user_email(db, bk.owner_id)
        renter_email = _user_email(db, bk.renter_id)
        if owner_email:
            send_email(
                owner_email,
                f"A reviewer was assigned for the deposit case — #{bk.id}",
                f"<p>A reviewer has been assigned to the deposit case for booking #{bk.id}.</p>"
                f'<p><a href="{case_url}">Case details</a></p>'
            )
        if renter_email:
            send_email(
                renter_email,
                f"A reviewer was assigned for the deposit case — #{bk.id}",
                f"<p>A reviewer has been assigned to the deposit case for booking #{bk.id}.</p>"
                f'<p><a href="{case_url}">Case details</a></p>'
            )
    except Exception:
        pass

    return RedirectResponse(f"/dm/deposits/{bk.id}", status_code=303)

# ===== DEBUG =====
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

# ===== 24h window =====
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
    if _is_closed(bk):
        raise HTTPException(status_code=400, detail="case already closed")

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
            db, bk.renter_id, "Alert: Pending Deduction Decision",
            f"There is a deduction decision of {amt} on your deposit for booking #{bk.id}. You have 24 hours to respond and upload evidence.",
            f"/deposits/{bk.id}/evidence/form", "deposit"
        )
        push_notification(
            db, bk.owner_id, "Renter Response Window Activated",
            f"A deduction decision of {amt} for booking #{bk.id} was opened. It will execute automatically after 24 hours if the renter does not respond.",
            f"/dm/deposits/{bk.id}", "deposit"
        )
        notify_admins(
            db, "Pending Deduction Decision",
            f"DM activated 24h window for booking #{bk.id} (amount={amt}).",
            f"/dm/deposits/{bk.id}"
        )
    except Exception:
        pass

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
                f"Alert: Deduction Decision on Your Deposit — #{bk.id}",
                f"<p>There is a deduction decision of {amt} CAD on your deposit for booking #{bk.id}."
                f" You have until <b>{deadline_str}</b> to respond and upload evidence.</p>"
                f'<p><a href="{ev_url}">Upload Evidence</a></p>'
            )
        if owner_email:
            send_email(
                owner_email,
                f"Renter Response Window Started — #{bk.id}",
                f"<p>A 24-hour window has been opened to execute a deduction decision of {amt} CAD."
                f" It will be executed automatically after the window ends unless the renter responds.</p>"
                f'<p><a href="{case_url}">Case Page</a></p>'
            )
        for em in admins_em:
            send_email(
                em,
                f"[Admin] awaiting_renter — #{bk.id}",
                f"<p>Proposed deduction of {amt} CAD for booking #{bk.id}.</p>"
                f'<p><a href="{case_url}">Open case</a></p>'
            )
        for em in dms_em:
            send_email(
                em,
                f"[DM] awaiting_renter — #{bk.id}",
                f"<p>The renter response window for a deduction decision has been opened for booking #{bk.id}.</p>"
                f'<p><a href="{case_url}">Manage case</a></p>'
            )
    except Exception:
        pass

    return RedirectResponse(url=f"/dm/deposits/{bk.id}?started=1", status_code=303)

# =========================
# >>> Internal: auto deduction after window ends
# =========================
def _auto_capture_for_booking(db: Session, bk: Booking) -> bool:
    now = datetime.utcnow()
    amt = int(getattr(bk, "dm_decision_amount", 0) or 0)
    if amt <= 0:
        return False
    if getattr(bk, "deposit_status", "") != "awaiting_renter":
        return False
    if getattr(bk, "renter_response_deadline_at", None) and bk.renter_response_deadline_at > now:
        return False
    if getattr(bk, "renter_response_at", None):
        return False
    if getattr(bk, "dm_decision", "") != "withhold":
        return False

    pi_id = _get_deposit_pi_id(bk)
    captured_ok = False
    charge_id = None

    if pi_id:
        try:
            pi = stripe.PaymentIntent.capture(pi_id, amount_to_capture=amt * 100)
            captured_ok = bool(pi and pi.get("status") in ("succeeded", "requires_capture") or True)
            charge_id = (pi.get("latest_charge")
                         or ((pi.get("charges") or {}).get("data") or [{}])[0].get("id"))
        except Exception:
            captured_ok = False

    bk.deposit_status = "partially_withheld" if captured_ok else "no_deposit"
    bk.deposit_charged_amount = (bk.deposit_charged_amount or 0) + (amt if captured_ok else 0)
    bk.status = "closed"
    bk.dm_decision_at = now
    bk.updated_at = now

    try:
        _audit(
            db, actor=None, bk=bk, action="auto_withhold_on_deadline",
            details={"amount": amt, "pi": pi_id, "captured": captured_ok, "charge_id": charge_id}
        )
    except Exception:
        pass

    db.commit()

    amt_txt = _fmt_money(amt)
    reason_txt = _short_reason(getattr(bk, "dm_decision_note", "") or "")
    try:
        push_notification(
            db, bk.owner_id, "Automatic Deduction Executed",
            f"{amt_txt} CAD was deducted from the deposit for booking #{bk.id}" + (f" — reason: {reason_txt}" if reason_txt else ""),
            f"/bookings/flow/{bk.id}", "deposit"
        )
        push_notification(
            db, bk.renter_id, "Automatic Deduction Executed",
            f"{amt_txt} CAD was deducted from your deposit for booking #{bk.id}" + (f" — reason: {reason_txt}" if reason_txt else ""),
            f"/bookings/flow/{bk.id}", "deposit"
        )
        notify_admins(db, "Automatic Deduction After Deadline", f"Booking #{bk.id} — {amt_txt} CAD.", f"/dm/deposits/{bk.id}")
        notify_dms(db, "Automatic Deduction After Deadline", f"Executed for booking #{bk.id}.", f"/dm/deposits/{bk.id}")
    except Exception:
        pass

    if captured_ok:
        try:
            owner: User = db.get(User, bk.owner_id)
            if owner and getattr(owner, "stripe_account_id", None) and getattr(owner, "payouts_enabled", False):
                stripe.Transfer.create(
                    amount=amt * 100, currency="cad",
                    destination=owner.stripe_account_id, source_transaction=charge_id
                )
        except Exception:
            pass

    return captured_ok

def cron_check_window(
    request: Request,
    db: Session = Depends(get_db),
    token: str | None = None,
):
    cron_token = os.getenv("CRON_TOKEN") or ""
    if cron_token:
        if token != cron_token:
            sess = request.session.get("user") or {}
            if not (sess.get("role") == "admin" or bool(sess.get("is_admin"))):
                raise HTTPException(status_code=403, detail="forbidden")

    rows = _deadline_overdue_rows(db)

    count = 0
    done = 0
    skipped = 0

    for bk in rows:
        count += 1
        try:
            ok = _auto_capture_for_booking(db, bk)
            if ok:
                done += 1
            else:
                skipped += 1
                try:
                    notify_dms(
                        db,
                        "Deadline Passed — Manual Intervention Needed",
                        f"Booking #{bk.id}: automatic deduction could not be performed.",
                        f"/dm/deposits/{bk.id}",
                    )
                    notify_admins(
                        db,
                        "Deadline Passed — Manual Intervention Needed",
                        f"Booking #{bk.id}: automatic deduction could not be performed.",
                        f"/dm/deposits/{bk.id}",
                    )
                except Exception:
                    pass
        except Exception:
            skipped += 1
            try:
                notify_admins(
                    db,
                    "Error During Automatic Deduction",
                    f"Booking #{bk.id}: an exception occurred during processing.",
                    f"/dm/deposits/{bk.id}",
                )
            except Exception:
                pass

    return {"checked": count, "captured": done, "needs_manual": skipped}

# public endpoint to run cron manually
@router.get("/dm/deposits/check-window")
def run_check_window(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = None
):
    return cron_check_window(request=request, db=db, token=token)

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

# ===== Simple nudge to renter to upload evidence =====
@router.post("/dm/deposits/{booking_id}/nudge-renter", response_model=None)
def dm_nudge_renter(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    note: Annotated[Optional[str], Form()] = None,
):
    sess = request.session.get("user") or {}
    if not (sess.get("role") == "admin" or sess.get("is_dm")):
        raise HTTPException(status_code=403, detail="forbidden")

    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="booking not found")
    if not bk.renter_id:
        raise HTTPException(status_code=400, detail="booking has no renter")

    link = f"/deposits/{booking_id}/evidence/form"
    msg = f"Please upload your evidence regarding the deposit for booking #{booking_id}.\nLink: {link}"
    if note:
        msg += f"\nNote: {note}"

    try:
        # Push notification
        push_notification(
            db=db,
            user_id=bk.renter_id,
            title="Request to Upload Deposit Evidence",
            body=msg,
            url=link,
        )

        # ==== EMAIL: DM nudged renter to upload evidence ====
        try:
            renter = db.get(User, bk.renter_id)
            owner = db.get(User, bk.owner_id)

            if renter and renter.email:
                subject = f"Action required — Upload your deposit evidence (Booking #{bk.id})"

                text_body = (
                    f"Dear {renter.first_name if renter else 'Renter'},\n\n"
                    f"The deposit manager is requesting that you upload your evidence for booking #{bk.id}.\n"
                    f"Please provide your photos/videos as soon as possible.\n\n"
                    f"Upload here: {BASE_URL}/deposits/{bk.id}/evidence/form"
                )

                html_body = f"""
                <div style="font-family:Arial,Helvetica,sans-serif; background:#f1f5f9; padding:30px;">
                    <div style="max-width:600px; margin:auto; background:white; padding:30px;
                                border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.08);">

                        <div style="text-align:center; margin-bottom:25px;">
                            <img src="https://sevor.net/static/img/sevor-logo.png" 
                                 style="width:120px; opacity:0.95;" />
                        </div>

                        <h2 style="color:#dc2626; margin-bottom:12px; text-align:center;">
                            Action Required ❗
                        </h2>

                        <p style="font-size:15px; color:#444;">
                            The deposit manager has requested that you upload your deposit evidence for 
                            booking <b>#{bk.id}</b>.
                        </p>

                        <p style="font-size:15px; color:#444;">
                            Please upload your photos/videos as soon as possible to avoid delays in your case.
                        </p>

                        <div style="text-align:center; margin:30px 0;">
                            <a href="{BASE_URL}/deposits/{bk.id}/evidence/form" 
                               style="background:#dc2626; color:white; padding:14px 24px; 
                                      text-decoration:none; border-radius:8px; font-size:16px;">
                                Upload Evidence
                            </a>
                        </div>

                        <hr style="border:none; border-top:1px solid #eee; margin:30px 0;">

                        <p style="font-size:13px; color:#888; text-align:center;">
                            Sevor — Rent anything worldwide
                        </p>
                    </div>
                </div>
                """

                send_email(
                    to=renter.email,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                )
        except Exception as e:
            print("EMAIL ERROR (DM NUDGE):", e)

    except Exception:
        pass

    request.session["flash_ok"] = "Notification sent to the renter."
    return RedirectResponse(url=f"/dm/deposits/{booking_id}", status_code=303)

@router.get("/bookings/{booking_id}/deposit/summary")
def deposit_final_summary(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    # must be owner or renter or DM/Admin
    bk = require_booking(db, booking_id)
    u = user
    if not u:
        raise HTTPException(status_code=401, detail="login required")
    is_participant = (u.id in (bk.owner_id, bk.renter_id))
    is_dm_or_admin = can_manage_deposits(u)
    if not (is_participant or is_dm_or_admin):
        raise HTTPException(status_code=403, detail="forbidden")

    item = db.get(Item, bk.item_id)
    # split renter evidence by phase
    renter_pickup, renter_return, renter_other = _split_renter_evidence(bk)

    return request.app.templates.TemplateResponse(
        "deposit_final_summary.html",
        {
            "request": request,
            "title": f"Final Result — #{bk.id}",
            "bk": bk,
            "item": item,
            "session_user": request.session.get("user"),
            "category_label": category_label,
            "renter_pickup": renter_pickup,
            "renter_return": renter_return,
            "renter_other": renter_other,
        },
    )

@router.post("/bookings/{booking_id}/pickup-proof-upload")
def renter_pickup_proof_upload(
    booking_id: int,
    files: List[UploadFile] | None = File(None),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="renter only")
    if (bk.status or "").lower() not in ("paid",):
        return RedirectResponse(url=f"/bookings/{bk.id}", status_code=303)

    saved_pairs = _save_evidence_files_and_cloud(bk.id, files)

    try:
        if DepositEvidence:
            for name, url in saved_pairs[:6]:
                db.add(DepositEvidence(
                    booking_id=bk.id,
                    uploader_id=user.id,
                    side="renter",
                    kind="image",
                    file_path=url,
                    description=_tagged_desc("pickup", comment),
                ))
            db.commit()
    except Exception:
        db.rollback()

    bk.status = "picked_up"
    bk.picked_up_at = datetime.utcnow()
    try:
        if (bk.payment_method or "") == "online":
            bk.owner_payout_amount = bk.rent_amount or 0
            bk.rent_released_at = datetime.utcnow()
            bk.online_status = "captured"
    except Exception:
        pass
    bk.updated_at = datetime.utcnow()
    db.commit()

    try:
        push_notification(
            db, bk.owner_id, "Picked Up",
            f"The renter confirmed pickup for booking #{bk.id} and uploaded pickup photos.",
            f"/bookings/flow/{bk.id}", "deposit"
        )

        # ==== EMAIL: Notify owner about pickup proof ====
        try:
            owner = db.get(User, bk.owner_id)
            renter = db.get(User, bk.renter_id)

            if owner and owner.email:
                subject = f"Pickup confirmed — Booking #{bk.id}"

                text_body = (
                    f"The renter {renter.first_name if renter else ''} "
                    f"has confirmed pickup for your item '{bk.id}' and uploaded pickup photos.\n"
                    f"Open booking: {BASE_URL}/bookings/flow/{bk.id}"
                )

                html_body = f"""
                <div style="font-family:Arial,Helvetica,sans-serif; background:#f8fafc; padding:30px;">
                    <div style="max-width:600px; margin:auto; background:white; padding:30px;
                                border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.06);">
                        
                        <div style="text-align:center; margin-bottom:25px;">
                            <img src="https://sevor.net/static/img/sevor-logo.png" 
                                 style="width:120px; opacity:0.95;" />
                        </div>

                        <h2 style="color:#16a34a; margin-bottom:10px; text-align:center;">
                            Pickup Confirmed 🎉
                        </h2>

                        <p style="font-size:15px; color:#444;">
                            The renter <b>{renter.first_name if renter else 'The renter'}</b> has confirmed pickup
                            and uploaded the required pickup photos for booking <b>#{bk.id}</b>.
                        </p>

                        <p style="font-size:15px; color:#444;">
                            You can now review the photos and continue the rental process.
                        </p>

                        <div style="text-align:center; margin:30px 0;">
                            <a href="{BASE_URL}/bookings/flow/{bk.id}" 
                               style="background:#16a34a; color:white; padding:14px 24px; 
                                      text-decoration:none; border-radius:8px; font-size:16px;">
                                Open Booking
                            </a>
                        </div>

                        <hr style="border:none; border-top:1px solid #eee; margin:30px 0;">

                        <p style="font-size:13px; color:#888; text-align:center;">
                            Sevor — Rent anything worldwide
                        </p>
                    </div>
                </div>
                """

                send_email(
                    to=owner.email,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                )
        except Exception as e:
            print("EMAIL ERROR (pickup proof):", e)

    except Exception:
        pass

    # ==== correct redirect
    try:
        next_url = (request.query_params.get("next") or "").strip() if request else ""
    except Exception:
        next_url = ""
    if not next_url:
        next_url = f"/bookings/flow/{bk.id}"
    return RedirectResponse(url=next_url, status_code=303)

@router.post("/bookings/{booking_id}/return-proof-upload")
def renter_return_proof_upload(
    booking_id: int,
    files: List[UploadFile] | None = File(None),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    request: Request = None,
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="renter only")
    if (bk.status or "").lower() not in ("picked_up",):
        return RedirectResponse(url=f"/bookings/{bk.id}", status_code=303)

    saved_pairs = _save_evidence_files_and_cloud(bk.id, files)

    try:
        if DepositEvidence:
            for name, url in saved_pairs[:6]:
                db.add(DepositEvidence(
                    booking_id=bk.id,
                    uploader_id=user.id,
                    side="renter",
                    kind="image",
                    file_path=url,
                    description=_tagged_desc("return", comment),
                ))
            db.commit()
    except Exception:
        db.rollback()

    bk.status = "returned"
    bk.returned_at = datetime.utcnow()
    bk.updated_at = datetime.utcnow()
    db.commit()

    try:
        push_notification(
            db, bk.owner_id, "Returned",
            f"The renter returned the item and uploaded return photos for booking #{bk.id}.",
            f"/bookings/flow/{bk.id}", "deposit"
        )

        # ==== EMAIL: Notify owner about return proof ====
        try:
            owner = db.get(User, bk.owner_id)
            renter = db.get(User, bk.renter_id)

            if owner and owner.email:
                subject = f"Item returned — Booking #{bk.id}"

                text_body = (
                    f"The renter {renter.first_name if renter else ''} "
                    f"returned the item and uploaded return photos for booking #{bk.id}.\n"
                    f"Open booking: {BASE_URL}/bookings/flow/{bk.id}"
                )

                html_body = f"""
                <div style="font-family:Arial,Helvetica,sans-serif; background:#f1f5f9; padding:30px;">
                    <div style="max-width:600px; margin:auto; background:white; padding:30px;
                                border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.06);">
                        
                        <div style="text-align:center; margin-bottom:25px;">
                            <img src="https://sevor.net/static/img/sevor-logo.png" 
                                 style="width:120px; opacity:0.95;" />
                        </div>

                        <h2 style="color:#2563eb; margin-bottom:10px; text-align:center;">
                            Item Returned ✔️
                        </h2>

                        <p style="font-size:15px; color:#444;">
                            The renter <b>{renter.first_name if renter else 'The renter'}</b> has returned your item
                            and uploaded the required return photos for booking <b>#{bk.id}</b>.
                        </p>

                        <p style="font-size:15px; color:#444;">
                            You can now review the return photos and finalize the deposit review.
                        </p>

                        <div style="text-align:center; margin:30px 0;">
                            <a href="{BASE_URL}/bookings/flow/{bk.id}" 
                               style="background:#2563eb; color:white; padding:14px 24px; 
                                      text-decoration:none; border-radius:8px; font-size:16px;">
                                View Booking Details
                            </a>
                        </div>

                        <hr style="border:none; border-top:1px solid #eee; margin:30px 0;">

                        <p style="font-size:13px; color:#888; text-align:center;">
                            Sevor — Rent anything worldwide
                        </p>
                    </div>
                </div>
                """

                send_email(
                    to=owner.email,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                )
        except Exception as e:
            print("EMAIL ERROR (return proof):", e)

    except Exception:
        pass

    # ==== correct redirect
    try:
        next_url = (request.query_params.get("next") or "").strip() if request else ""
    except Exception:
        next_url = ""
    if not next_url:
        next_url = f"/reviews/renter/{bk.id}"
    return RedirectResponse(url=next_url, status_code=303)
