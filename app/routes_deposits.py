# app/routes_deposits.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Literal

from .database import get_db
from .models import Booking, User
from .notifications_api import push_notification, notify_admins

router = APIRouter(tags=["deposits"])


# ---------- المساعدة ----------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None


def require_auth(user: Optional[User]):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_booking(db: Session, booking_id: int) -> Booking:
    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    return bk


# ---------- فتح بلاغ من المالك ----------
@router.post("/deposits/{booking_id}/report")
async def report_deposit_issue(
    booking_id: int,
    issue_type: Literal["delay", "damage", "loss", "theft"] = Form(...),
    description: str = Form(""),
    request: Request = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can report issue")
    if bk.status not in ["returned", "picked_up"]:
        raise HTTPException(status_code=400, detail="Invalid state")

    bk.deposit_status = "in_dispute"
    bk.status = "in_review"
    bk.updated_at = datetime.utcnow()
    db.commit()

    # إشعارات
    push_notification(
        db,
        bk.renter_id,
        "بلاغ وديعة جديد",
        f"قام المالك بالإبلاغ عن مشكلة ({issue_type}) بخصوص الغرض '{bk.item_id}'.",
        f"/bookings/flow/{bk.id}",
        "deposit"
    )
    notify_admins(db, "مراجعة ديبو مطلوبة", f"بلاغ جديد بخصوص حجز #{bk.id}.", f"/bookings/flow/{bk.id}")

    return RedirectResponse(f"/bookings/flow/{bk.id}", status_code=303)


# ---------- رد المستأجر ----------
@router.post("/deposits/{booking_id}/renter-response")
async def renter_response_to_issue(
    booking_id: int,
    renter_comment: str = Form(""),
    request: Request = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can respond")
    if bk.deposit_status != "in_dispute":
        raise HTTPException(status_code=400, detail="No open deposit issue")

    # هنا يمكن مستقبلاً حفظ الرد في جدول منفصل audit أو deposit_log
    bk.updated_at = datetime.utcnow()
    db.commit()

    push_notification(
        db,
        bk.owner_id,
        "رد من المستأجر",
        f"رد المستأجر على بلاغ الوديعة لحجز #{bk.id}.",
        f"/bookings/flow/{bk.id}",
        "deposit"
    )
    notify_admins(db, "رد وديعة جديد", f"رد المستأجر في قضية حجز #{bk.id}.", f"/bookings/flow/{bk.id}")

    return RedirectResponse(f"/bookings/flow/{bk.id}", status_code=303)


# ---------- قرار متحكم الوديعة أو الأدمن ----------
@router.post("/deposits/{booking_id}/decision")
async def deposit_final_decision(
    booking_id: int,
    decision: Literal["refund_all", "refund_partial", "withhold_all"] = Form(...),
    amount: int = Form(0),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    if not user.can_manage_deposits:
        raise HTTPException(status_code=403, detail="No permission")

    bk = require_booking(db, booking_id)
    if bk.deposit_status not in ["in_dispute", "held"]:
        raise HTTPException(status_code=400, detail="Invalid deposit state")

    refunded = 0
    withheld = 0

    if decision == "refund_all":
        refunded = bk.deposit_amount
        bk.deposit_status = "refunded"
    elif decision == "refund_partial":
        refunded = max(0, bk.deposit_amount - amount)
        withheld = amount
        bk.deposit_status = "partially_refunded"
    elif decision == "withhold_all":
        refunded = 0
        withheld = bk.deposit_amount
        bk.deposit_status = "claimed"

    bk.status = "closed"
    bk.updated_at = datetime.utcnow()
    db.commit()

    # إشعارات
    push_notification(
        db,
        bk.owner_id,
        "قرار الوديعة",
        f"تم اتخاذ قرار نهائي: {decision}.",
        f"/bookings/flow/{bk.id}",
        "deposit"
    )
    push_notification(
        db,
        bk.renter_id,
        "قرار الوديعة",
        f"تم اتخاذ قرار نهائي بخصوص الوديعة: {decision}.",
        f"/bookings/flow/{bk.id}",
        "deposit"
    )

    return RedirectResponse(f"/bookings/flow/{bk.id}", status_code=303)
