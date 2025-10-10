# app/routes_deposits.py
from __future__ import annotations
from typing import Optional, Literal, List, Dict
from datetime import datetime

import os
import stripe
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, Item, User
from .notifications_api import push_notification, notify_admins

router = APIRouter(tags=["deposits"])

# ============ Stripe ============
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")


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


# ============ قائمة القضايا ============
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

    q = (
        db.query(Booking)
        .filter(
            (Booking.deposit_hold_intent_id.isnot(None))
            | (Booking.deposit_status.in_(["held", "in_dispute", "partially_withheld"]))
            | (Booking.status.in_(["returned", "in_review"]))
        )
        .order_by(Booking.updated_at.desc() if hasattr(Booking, "updated_at") else Booking.id.desc())
    )
    cases: List[Booking] = q.all()

    # خريطة العناصر لعرض العناوين في الجدول
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


# ============ صفحة القضية ============
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

    return request.app.templates.TemplateResponse(
        "dm_case.html",
        {
            "request": request,
            "title": f"قضية وديعة #{bk.id}",
            "session_user": request.session.get("user"),
            "bk": bk,
            "item": item,
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
        # لا يوجد تفويض فعّال
        return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

    deposit_total = max(0, bk.deposit_amount or bk.hold_deposit_amount or 0)

    try:
        if decision == "release":
            # إلغاء التفويض بالكامل
            stripe.PaymentIntent.cancel(pi_id)
            bk.deposit_status = "refunded"
            bk.deposit_charged_amount = 0
            _audit(db, actor=user, bk=bk, action="deposit_release_all", details={"reason": reason})

        elif decision == "withhold":
            amt = max(0, int(amount or 0))
            if amt <= 0:
                raise HTTPException(status_code=400, detail="Invalid amount")
            if amt >= deposit_total:
                # خصم كامل
                stripe.PaymentIntent.capture(pi_id, amount_to_capture=deposit_total * 100)
                bk.deposit_status = "claimed"
                bk.deposit_charged_amount = deposit_total
                _audit(db, actor=user, bk=bk, action="deposit_withhold_all", details={"amount": deposit_total, "reason": reason})
            else:
                # خصم جزئي
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

    # أغلق القضية / حدّث سجل الحجز
    bk.status = "closed"
    bk.updated_at = datetime.utcnow()
    if reason:
        # إن كان لديك عمود owner_return_note فحدّثه (آمن إن لم يوجد)
        try:
            setattr(bk, "owner_return_note", reason)
        except Exception:
            pass

    db.commit()

    # إشعارات للمالك والمستأجر + تنبيه للأدمن
    push_notification(
        db, bk.owner_id, "قرار الوديعة", f"تم تنفيذ قرار الوديعة لحجز #{bk.id}.", f"/bookings/flow/{bk.id}", "deposit"
    )
    push_notification(
        db, bk.renter_id, "قرار الوديعة", f"صدر القرار النهائي بخصوص وديعة حجز #{bk.id}.", f"/bookings/flow/{bk.id}", "deposit"
    )
    notify_admins(db, "قرار وديعة مُنفَّذ", f"قرار {decision} لحجز #{bk.id}.", f"/bookings/flow/{bk.id}")

    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)


# ===================== [إضافات وفق الخطة] =====================

# 1) تسجيل تدقيقي اختياري (لا يكسر لو الجدول غير موجود)
from sqlalchemy import text
from .database import engine as _engine

def _audit(db: Session, actor: Optional[User], bk: Booking, action: str, details: dict | None = None):
    """
    يكتب سجلًا في جدول deposit_audit_log إذا كان موجودًا.
    الحقول المقترحة في الجدول:
      id, booking_id, actor_id, role, action, details(json/text), created_at
    """
    try:
        # نفحص الجدول مرة واحدة تقريبًا
        with _engine.begin() as conn:
            rows = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='deposit_audit_log'").all()
            if not rows:
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
        # لا شيء — سجّل بصمت بدون كسر التدفق
        pass


# 2) بلاغ المالك عن مشكلة عند الإرجاع
@router.post("/deposits/{booking_id}/report")
def report_deposit_issue(
    booking_id: int,
    issue_type: Literal["delay", "damage", "loss", "theft"] = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يستخدمه المالك بعد الإرجاع أو أثناءه لفتح قضية وديعة.
    يضبط:
      - booking.deposit_status = 'in_dispute'
      - booking.status = 'in_review'
      - booking.owner_return_note = description (إن وُجد العمود)
    ويرسل إشعارات للطرفين ويُسجّل في الـ Audit (إن وُجد الجدول).
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can report issue")

    # لا نقيّد بالحالة كثيرًا، لكن منطقيًا يكون بعد returned/picked_up
    if getattr(bk, "deposit_hold_intent_id", None) is None:
        raise HTTPException(status_code=400, detail="No deposit hold found")

    bk.deposit_status = "in_dispute"
    bk.status = "in_review"
    bk.updated_at = datetime.utcnow()
    # ملاحظة المالك
    try:
        if description:
            setattr(
                bk,
                "owner_return_note",
                (getattr(bk, "owner_return_note", "") or "").strip()
                + (("\n" if getattr(bk, "owner_return_note", "") else "") + f"[{issue_type}] {description}")
            )
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
    notify_admins(db, "مراجعة ديبو مطلوبة", f"بلاغ جديد بخصوص حجز #{bk.id}.", f"/bookings/flow/{bk.id}")

    # سجل تدقيقي
    _audit(db, actor=user, bk=bk, action="owner_report_issue", details={"issue_type": issue_type, "desc": description})

    return RedirectResponse(f"/bookings/flow/{bk.id}", status_code=303)


# 3) ردّ المستأجر على البلاغ
@router.post("/deposits/{booking_id}/renter-response")
def renter_response_to_issue(
    booking_id: int,
    renter_comment: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يتيح للمستأجر إضافة رده على بلاغ الوديعة المفتوح.
    لا يغيّر القرار؛ فقط يسجّل التعليق ويُخطِر المالك/الإدارة.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can respond")
    if bk.deposit_status != "in_dispute":
        raise HTTPException(status_code=400, detail="No open deposit issue")

    # تحديث وقت
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
    notify_admins(db, "رد وديعة جديد", f"ردّ المستأجر في قضية حجز #{bk.id}.", f"/bookings/flow/{bk.id}")

    # سجل تدقيقي
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

    # لو العمود موجود — عين المراجع
    try:
        current = getattr(bk, "dm_assignee_id")
        if current in (None, 0):
            setattr(bk, "dm_assignee_id", user.id)
            setattr(bk, "updated_at", datetime.utcnow())
            _audit(db, actor=user, bk=bk, action="dm_claim_case", details={})
            db.commit()
    except Exception:
        # لا عمود — تجاهُل
        pass

    return RedirectResponse(f"/dm/deposits/{bk.id}", status_code=303)