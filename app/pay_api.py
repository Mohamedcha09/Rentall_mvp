# app/pay_api.py
from __future__ import annotations

import os
import base64
import requests
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
# PAYPAL CORE (REAL)
# =====================================================

PAYPAL_BASE = "https://api-m.sandbox.paypal.com"  # LIVE لاحقًا

def paypal_get_token() -> str:
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    secret = os.getenv("PAYPAL_SECRET")

    if not client_id or not secret:
        raise RuntimeError("PayPal credentials missing")

    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()

    r = requests.post(
        f"{PAYPAL_BASE}/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def paypal_create_order(
    *,
    booking: Booking,
    amount: float,
    currency: str,
    pay_type: Literal["rent", "securityfund"],
) -> str:
    token = paypal_get_token()

    label = "Rent payment" if pay_type == "rent" else "Security fund"

    r = requests.post(
        f"{PAYPAL_BASE}/v2/checkout/orders",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": f"{pay_type.upper()}_{booking.id}",
                    "description": label,
                    "amount": {
                        "currency_code": currency,
                        "value": f"{amount:.2f}",
                    },
                }
            ],
            "application_context": {
                "brand_name": "Sevor",
                "user_action": "PAY_NOW",
                "return_url": (
                    f"https://sevor.net/paypal/return"
                    f"?booking_id={booking.id}&type={pay_type}"
                ),
                "cancel_url": f"https://sevor.net/bookings/flow/{booking.id}",
            },
        },
        timeout=20,
    )

    r.raise_for_status()
    data = r.json()

    for link in data.get("links", []):
        if link.get("rel") == "approve":
            return link["href"]

    raise RuntimeError("PayPal approval link not found")


def paypal_capture(order_id: str):
    token = paypal_get_token()

    r = requests.post(
        f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()

# =====================================================
# PAYPAL START
# =====================================================

@router.get("/paypal/start/{booking_id}")
def paypal_start(
    booking_id: int,
    type: Literal["rent", "securityfund"],
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403)

    if type == "rent":
        if bk.rent_paid:
            raise HTTPException(status_code=400, detail="Rent already paid")
        amount = bk.total_amount

    else:  # securityfund
        if bk.security_amount <= 0:
            raise HTTPException(status_code=400, detail="No security fund required")
        if bk.security_paid:
            raise HTTPException(status_code=400, detail="Security fund already paid")
        amount = bk.security_amount

    approval_url = paypal_create_order(
        booking=bk,
        amount=amount,
        currency=(bk.currency or "CAD"),
        pay_type=type,
    )

    return RedirectResponse(approval_url, status_code=302)

# =====================================================
# PAYPAL RETURN
# =====================================================

@router.get("/paypal/return")
def paypal_return(
    booking_id: int,
    type: Literal["rent", "securityfund"],
    token: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403)

    paypal_capture(token)

    if type == "rent":
        if not bk.rent_paid:
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

    else:  # securityfund
        if not bk.security_paid:
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
                "security",
            )

    if bk.rent_paid and (bk.security_paid or bk.security_amount == 0):
        bk.status = "paid"
        bk.timeline_paid_at = datetime.utcnow()

    db.commit()

    flag = "rent_ok" if type == "rent" else "security_ok"
    return flow_redirect(bk, flag)
