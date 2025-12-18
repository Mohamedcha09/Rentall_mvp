# app/pay_api.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, User
from .notifications_api import push_notification, notify_admins

router = APIRouter(tags=["payments"])

# =========================================================
# Helpers
# =========================================================

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


def can_manage_deposits(user: User) -> bool:
    return bool(
        (user.role or "").lower() == "admin"
        or getattr(user, "is_deposit_manager", False)
    )


def flow_redirect(booking_id: int) -> RedirectResponse:
    return RedirectResponse(
        url=f"/bookings/flow/{booking_id}",
        status_code=303
    )

# =========================================================
# STEP 1 — User confirms payment was done on PayPal
# (rent + deposit together OR rent only)
# =========================================================

@router.post("/api/paypal/confirm-payment/{booking_id}")
def confirm_paypal_payment(
    booking_id: int,
    rent_paid: bool = Form(True),
    security_paid: bool = Form(False),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    This endpoint is called AFTER the user completes PayPal payment.
    PayPal is NOT trusted — we only mark internal state.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can confirm payment")

    # --- RENT ---
    if rent_paid:
        bk.rent_paid = True
        bk.payment_status = "paid"

    # --- SECURITY / DEPOSIT ---
    if security_paid:
        bk.security_paid = True
        bk.security_status = "held"

    # Global status
    if bk.rent_paid and (not bk.security_amount or bk.security_paid):
        bk.status = "paid"
        bk.timeline_paid_at = datetime.utcnow()

    db.commit()

    # Notifications
    push_notification(
        db,
        bk.owner_id,
        "Payment received",
        f"Booking #{bk.id}: renter completed payment.",
        f"/bookings/flow/{bk.id}",
        "booking"
    )

    push_notification(
        db,
        bk.renter_id,
        "Payment confirmed",
        f"Your payment for booking #{bk.id} is recorded.",
        f"/bookings/flow/{bk.id}",
        "booking"
    )

    return flow_redirect(bk.id)

# =========================================================
# STEP 2 — Owner confirms return & declares damage
# =========================================================

@router.post("/api/deposit/owner-decision/{booking_id}")
def owner_deposit_decision(
    booking_id: int,
    damage_amount: float = Form(0),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    Owner declares if there is damage.
    This does NOT move money — only updates DB.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can submit decision")

    if not bk.security_paid:
        raise HTTPException(status_code=400, detail="No deposit paid")

    bk.damage_amount = damage_amount
    bk.refund_amount = max(float(bk.security_amount or 0) - damage_amount, 0)
    bk.security_status = "under_review"
    bk.owner_return_note = note
    bk.return_confirmed_by_owner_at = datetime.utcnow()

    db.commit()

    notify_admins(
        db,
        "Deposit review required",
        f"Booking #{bk.id}: owner submitted return decision.",
        f"/bookings/flow/{bk.id}"
    )

    return JSONResponse({"ok": True})

# =========================================================
# STEP 3 — Admin / Deposit Manager final decision
# =========================================================

@router.post("/api/deposit/finalize/{booking_id}")
def finalize_deposit(
    booking_id: int,
    action: Literal["refund_all", "refund_partial", "withhold_all"] = Form(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    FINAL decision.
    This is where Sevor decides what happens with money.
    """
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Not allowed")

    bk = require_booking(db, booking_id)

    deposit = float(bk.security_amount or 0)
    damage = float(bk.damage_amount or 0)

    if action == "refund_all":
        bk.refund_amount = deposit
        bk.owner_due_amount = 0
        bk.security_status = "refunded"

    elif action == "refund_partial":
        bk.refund_amount = max(deposit - damage, 0)
        bk.owner_due_amount = min(damage, deposit)
        bk.security_status = "partially_withheld"

    elif action == "withhold_all":
        bk.refund_amount = 0
        bk.owner_due_amount = deposit
        bk.security_status = "claimed"

    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    bk.refund_done = False   # money not sent yet
    bk.payout_executed = False
    bk.dm_decision_at = datetime.utcnow()

    db.commit()

    # Notifications
    push_notification(
        db,
        bk.renter_id,
        "Deposit decision",
        f"Decision finalized for booking #{bk.id}.",
        f"/bookings/flow/{bk.id}",
        "deposit"
    )

    push_notification(
        db,
        bk.owner_id,
        "Deposit decision finalized",
        f"Booking #{bk.id}: decision completed.",
        f"/bookings/flow/{bk.id}",
        "deposit"
    )

    return JSONResponse({"ok": True})

# =========================================================
# STEP 4 — Mark refund / payout as DONE (manual or bot)
# =========================================================

@router.post("/api/deposit/mark-executed/{booking_id}")
def mark_money_executed(
    booking_id: int,
    refund_done: bool = Form(False),
    payout_done: bool = Form(False),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    This is called AFTER money is sent via PayPal manually or by bot.
    """
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Not allowed")

    bk = require_booking(db, booking_id)

    if refund_done:
        bk.refund_done = True

    if payout_done:
        bk.payout_executed = True
        bk.payout_executed_at = datetime.utcnow()

    db.commit()

    return JSONResponse({"ok": True})

@router.get("/paypal/start/{booking_id}")
def paypal_start(
    booking_id: int,
    type: Literal["rent", "deposit"] = "rent",
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403)

    if type == "rent" and bk.rent_paid:
        raise HTTPException(status_code=400, detail="Rent already paid")

    if type == "deposit" and bk.security_paid:
        raise HTTPException(status_code=400, detail="Deposit already paid")

    # هنا لاحقاً نضيف PayPal SDK
    return RedirectResponse(
        url=f"/paypal/redirect-mock?booking_id={bk.id}&type={type}",
        status_code=302
    )


@router.get("/paypal/return")
def paypal_return(
    booking_id: int,
    type: Literal["rent", "deposit"],
    db: Session = Depends(get_db),
):
    bk = require_booking(db, booking_id)

    if type == "rent":
        bk.rent_paid = True
        bk.payment_status = "paid"

    if type == "deposit":
        bk.security_paid = True
        bk.security_status = "held"

    if bk.rent_paid and (bk.security_paid or bk.security_amount == 0):
        bk.status = "paid"
        bk.timeline_paid_at = datetime.utcnow()

    db.commit()

    # نرجع للـ flow مع flag
    flag = "rent_ok" if type == "rent" else "deposit_ok"
    return RedirectResponse(
        url=f"/bookings/flow/{bk.id}?{flag}=1",
        status_code=302
    )
