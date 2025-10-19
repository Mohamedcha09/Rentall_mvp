from __future__ import annotations
from typing import Optional
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Booking, Item
from .notifications_api import push_notification

router = APIRouter()

# ---------- عام ----------
def _require_login(request: Request):
    return request.session.get("user")

@router.get("/disputes/new")
def dispute_new(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "dispute_new.html",
        {"request": request, "session_user": u, "title": "فتح نزاع"}
    )

# ---------- Helpers مشتركة ----------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None

def require_dm(user: Optional[User]):
    # ملاحظة: الملف الرسمي يستخدم is_deposit_manager/admin، هنا نحافظ على can_manage_deposits للتوافق
    if not user or not getattr(user, "can_manage_deposits", False):
        raise HTTPException(status_code=403, detail="Deposit Manager only")

def _stripe():
    try:
        import stripe
        sk = os.getenv("STRIPE_SECRET_KEY", "")
        if not sk:
            return None
        stripe.api_key = sk
        return stripe
    except Exception:
        return None

def _notify_after_decision(db: Session, bk: Booking, title_owner: str, title_renter: str, body: str):
    """
    بعد قرار متحكّم الوديعة، نوجّه كلا الطرفين إلى صفحة القضية.
    """
    link = f"/dm/deposits/{bk.id}"
    push_notification(db, bk.owner_id, title_owner, body, link, "deposit")
    push_notification(db, bk.renter_id, title_renter, body, link, "deposit")

# ============================================================
# ⚠️ نُقِلَت مسارات DM هنا إلى Prefix "dm-compat" لمنع التعارض
# ============================================================

@router.get("/dm-compat/deposits")
def dm_queue_compat(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    نسخة توافقية لا تتعارض مع المسار الرسمي في routes_deposits.py
    يُفضّل استخدام /dm/deposits من الملف الرسمي.
    """
    require_dm(user)

    q = (
        db.query(Booking)
        .filter((Booking.hold_deposit_amount > 0))
        .order_by(Booking.returned_at.desc().nullslast(), Booking.created_at.desc())
    )
    cases = q.all()

    items_map = {}
    if cases:
        item_ids = list({b.item_id for b in cases})
        for it in db.query(Item).filter(Item.id.in_(item_ids)).all():
            items_map[it.id] = it

    return request.app.templates.TemplateResponse(
        "dm_queue.html",
        {
            "request": request,
            "title": "قضايا الوديعة (توافق)",
            "session_user": request.session.get("user"),
            "cases": cases,
            "items_map": items_map,
        },
    )


@router.get("/dm-compat/deposits/{booking_id}")
def dm_case_compat(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    شاشة ملف وديعة (نسخة توافقية). المسار الرسمي: /dm/deposits/{booking_id} في routes_deposits.py
    """
    require_dm(user)

    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")

    item = db.get(Item, bk.item_id) if bk.item_id else None
    owner = db.get(User, bk.owner_id) if bk.owner_id else None
    renter = db.get(User, bk.renter_id) if bk.renter_id else None

    return request.app.templates.TemplateResponse(
        "dm_case.html",
        {
            "request": request,
            "title": f"قضية وديعة #{bk.id} (توافق)",
            "session_user": request.session.get("user"),
            "booking": bk,  # الاسم الذي قد يعتمد عليه القالب
            "bk": bk,       # والتسمية القديمة أيضاً
            "item": item,
            "item_title": (item.title if item else "—"),
            "owner": owner,
            "renter": renter,
        },
    )


@router.post("/dm-compat/deposits/{booking_id}/decision")
def dm_decide_compat(
    booking_id: int,
    decision: str = Form(...),  # 'release' or 'withhold'
    amount: int = Form(0),
    reason: str = Form(""),
    request: Request = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    تنفيذ قرار (نسخة توافقية). المسار الرسمي موجود في routes_deposits.py
    """
    require_dm(user)
    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")

    if (bk.hold_deposit_amount or 0) <= 0:
        raise HTTPException(status_code=400, detail="No deposit on this booking")

    stripe = _stripe()
    updated_note = (bk.owner_return_note or "").strip()

    if decision == "release":
        if stripe and getattr(bk, "deposit_hold_intent_id", None):
            try:
                stripe.PaymentIntent.cancel(bk.deposit_hold_intent_id)
            except Exception:
                pass

        bk.deposit_status = "released"
        bk.updated_at = datetime.utcnow()
        if updated_note:
            updated_note += "\n"
        updated_note += f"[DM] Release full deposit. Reason: {reason or '—'}"
        bk.owner_return_note = updated_note
        db.commit()

        _notify_after_decision(
            db, bk,
            "تم الإفراج عن الوديعة",
            "تم الإفراج عن وديعتك",
            f"قرار متحكّم الوديعة: إفراج كامل. السبب: {reason or '—'}",
        )
        return RedirectResponse(url=f"/dm/deposits/{bk.id}", status_code=303)

    # withhold
    amount = max(0, int(amount or 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    if amount > (bk.hold_deposit_amount or 0):
        amount = bk.hold_deposit_amount or 0

    captured_ok = False
    if stripe and getattr(bk, "deposit_hold_intent_id", None):
        try:
            amt_cents = int(amount * 100)
            pi = stripe.PaymentIntent.capture(
                bk.deposit_hold_intent_id,
                amount_to_capture=amt_cents
            )
            try:
                charge_id = (pi.get("latest_charge") or "") if isinstance(pi, dict) else None
                if charge_id and hasattr(bk, "deposit_capture_id"):
                    bk.deposit_capture_id = str(charge_id)
            except Exception:
                pass
            captured_ok = True

            try:
                remaining = (bk.hold_deposit_amount or 0) - (bk.deposit_charged_amount or 0) - amount
                if remaining > 0:
                    stripe.PaymentIntent.cancel(bk.deposit_hold_intent_id)
            except Exception:
                pass
        except Exception:
            captured_ok = False

    bk.deposit_charged_amount = (bk.deposit_charged_amount or 0) + amount
    if bk.deposit_charged_amount >= (bk.hold_deposit_amount or 0):
        bk.deposit_status = "claimed"
    else:
        bk.deposit_status = "partially_refunded"

    bk.updated_at = datetime.utcnow()

    if updated_note:
        updated_note += "\n"
    updated_note += f"[DM] Withhold {amount}$ . Reason: {reason or '—'} (stripe_ok={captured_ok})"
    bk.owner_return_note = updated_note

    db.commit()

    _notify_after_decision(
        db, bk,
        "قرار وديعة: اقتطاع للمالك",
        "قرار وديعة: تم اقتطاع جزء من وديعتك",
        f"المبلغ المقتطع: {amount}$ — السبب: {reason or '—'}",
    )
    return RedirectResponse(url=f"/dm/deposits/{bk.id}", status_code=303)


# ------------------------------------------------------------
# ✅ إصلاح التعارض مع صفحة البلاغ الرسمية:
#   كان هذا الملف يُعرِّف GET /deposits/{booking_id}/report كـ Redirect
#   وهذا يُخفي صفحة النموذج الحقيقية (الموجودة في routes_deposits.py).
#   نقلناه لمسار LEGACY منفصل آمن:
# ------------------------------------------------------------
@router.get("/deposits/{booking_id}/report-legacy")
def deposit_report_legacy_redirect(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    مسار قديم للروابط التاريخية فقط.
    - لو المستخدم DM → نرسله لصفحة القضية /dm/deposits/{id}
    - غير ذلك → نرسله لتدفّق الحجز /bookings/flow/{id}
    صفحة النموذج الرسمية موجودة على: GET /deposits/{booking_id}/report (في routes_deposits.py)
    """
    if user and getattr(user, "can_manage_deposits", False):
        return RedirectResponse(url=f"/dm/deposits/{booking_id}", status_code=303)
    return RedirectResponse(url=f"/bookings/flow/{booking_id}", status_code=303)