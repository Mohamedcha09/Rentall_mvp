# app/pay_api.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, User
from .notifications_api import push_notification

router = APIRouter(tags=["payments"])

# =====================================================
# Helpers
# =====================================================

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
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


def flow_redirect(bk: Booking, flag: str | None = None):
    url = f"/bookings/flow/{bk.id}"
    if flag:
        url += f"?{flag}=1"
    return RedirectResponse(url=url, status_code=303)

# =====================================================
# PAYPAL START (Rent / Security)
# =====================================================

@router.get("/paypal/start/{booking_id}")
def paypal_start(
    booking_id: int,
    type: Literal["rent", "security"],
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    # 🔐 فقط المستأجر
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403)

    # 🧾 Rent
    if type == "rent":
        if bk.rent_paid:
            raise HTTPException(status_code=400, detail="Rent already paid")

    # 🛡️ Security
    if type == "security":
        if bk.security_amount <= 0:
            raise HTTPException(status_code=400, detail="No security fund required")
        if bk.security_paid:
            raise HTTPException(status_code=400, detail="Security fund already paid")

    # 🔴 مؤقت: redirect مباشر (Mock PayPal)
    return RedirectResponse(
        url=f"/paypal/return?booking_id={bk.id}&type={type}",
        status_code=302,
    )

# =====================================================
# PAYPAL RETURN (SINGLE & CORRECT)
# =====================================================

@router.get("/paypal/return")
def paypal_return(
    booking_id: int,
    type: Literal["rent", "security"],
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    # 🔐 تأكيد أن نفس المستأجر
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403)

    # =========================
    # RENT PAYMENT
    # =========================
    if type == "rent":
        if bk.rent_paid:
            return flow_redirect(bk, "rent_ok")

        bk.rent_paid = True
        bk.payment_status = "paid"
        bk.payment_method = "paypal"

        push_notification(
            db,
            bk.owner_id,
            "Rent paid",
            f"Booking #{bk.id}: rent paid via PayPal.",
            f"/bookings/flow/{bk.id}",
            "payment",
        )

    # =========================
    # SECURITY PAYMENT
    # =========================
    elif type == "security":
        if bk.security_paid:
            return flow_redirect(bk, "security_ok")

        bk.security_paid = True
        bk.security_status = "held"
        bk.payment_status = "paid"
        bk.payment_method = "paypal"

        push_notification(
            db,
            bk.owner_id,
            "Security fund paid",
            f"Booking #{bk.id}: security fund is now held.",
            f"/bookings/flow/{bk.id}",
            "deposit",
        )

    # =========================
    # FINAL STATUS
    # =========================
    if bk.rent_paid and (bk.security_paid or bk.security_amount == 0):
        bk.status = "paid"
        bk.timeline_paid_at = datetime.utcnow()

    db.commit()

    flag = "rent_ok" if type == "rent" else "security_ok"
    return flow_redirect(bk, flag)


def confirm_paypal_payment(*args, **kwargs):
    raise NotImplementedError("confirm_paypal_payment not implemented yet")
