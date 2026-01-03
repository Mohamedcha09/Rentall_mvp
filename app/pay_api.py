# =====================================================
# pay-api.py
# =====================================================

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

# ✅ نستخدم نفس منطق الضرائب
from .utili_geo import locate_from_session
from .utili_tax import compute_order_taxes

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


def flow_redirect(bk: Booking, flag: str):
    return RedirectResponse(
        url=f"/bookings/flow/{bk.id}?{flag}=1",
        status_code=303,
    )

# =====================================================
# PayPal core
# =====================================================

PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")

if PAYPAL_MODE == "live":
    PAYPAL_BASE = "https://api-m.paypal.com"
else:
    PAYPAL_BASE = "https://api-m.sandbox.paypal.com"

def paypal_get_token() -> str:
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    secret = os.getenv("PAYPAL_CLIENT_SECRET")

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

def compute_grand_total_for_paypal(request: Request, bk: Booking) -> dict:
    rent = float(bk.total_amount or 0)

    SEVOR_FEE_PCT = 0.02
    PAYPAL_PCT = 0.029
    PAYPAL_FIXED = 0.30

    sevor_fee = round(rent * SEVOR_FEE_PCT, 2)

    base = rent + sevor_fee
    paypal_fee = round(base * PAYPAL_PCT + PAYPAL_FIXED, 2)

    grand_total = round(rent + sevor_fee + paypal_fee, 2)

    # تخزين القيم (snapshot)
    bk.platform_fee = sevor_fee
    bk.owner_due_amount = rent
    bk.amount_paid_cents = int(grand_total * 100)

    return {
        "rent": rent,
        "sevor_fee": sevor_fee,
        "paypal_fee": paypal_fee,
        "grand_total": grand_total,
    }

@router.get("/paypal/start/{booking_id}")
def paypal_start(
    booking_id: int,
    type: Literal["rent", "securityfund"],
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403)

    if type == "rent":
        if bk.rent_paid:
            raise HTTPException(status_code=400)

        # ✅ هنا التغيير المهم
        pricing = compute_grand_total_for_paypal(request, bk)
        amount = pricing["grand_total"]


    else:
        # Security fund — بدون ضرائب
        if bk.security_amount <= 0 or bk.security_paid:
            raise HTTPException(status_code=400)
        amount = float(bk.security_amount)

    approval_url = paypal_create_order(
        booking=bk,
        amount=amount,
        currency=(bk.currency or "CAD"),
        pay_type=type,
    )

    return RedirectResponse(approval_url, status_code=302)

# =====================================================
# RETURN + CAPTURE
# =====================================================

# =====================================================
# RETURN + CAPTURE (FIXED)
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

    capture_data = paypal_capture(token)

    cap = capture_data["purchase_units"][0]["payments"]["captures"][0]
    capture_id = cap["id"]
    capture_status = (cap.get("status") or "").upper()

    # ✅ تصحيح أساسي
    bk.payment_method = "paypal"
    bk.payment_provider = "paypal"
    bk.paypal_order_id = token

    if capture_status != "COMPLETED":
        if type == "rent":
            bk.paypal_capture_id = capture_id
            bk.payment_status = "pending"
        else:
            bk.deposit_capture_id = capture_id
            bk.security_status = "pending"

        db.commit()
        return flow_redirect(bk, "paypal_pending")

    if type == "rent":
        bk.rent_paid = True
        bk.payment_status = "paid"
        bk.paypal_capture_id = capture_id
    else:
        bk.security_paid = True
        bk.security_status = "held"
        bk.deposit_status = "held"
        bk.deposit_capture_id = capture_id

    if bk.rent_paid and (bk.security_paid or bk.security_amount == 0):
        bk.status = "paid"
        bk.timeline_paid_at = datetime.utcnow()

    db.commit()
    return flow_redirect(bk, "rent_ok" if type == "rent" else "security_ok")

# =====================================================
# DEPOSIT REFUND (ROBOT ONLY)
# =====================================================

def paypal_refund_capture(
    *,
    capture_id: str,
    amount: float,
    currency: str,
) -> str:
    token = paypal_get_token()

    r = requests.post(
        f"{PAYPAL_BASE}/v2/payments/captures/{capture_id}/refund",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "amount": {
                "value": f"{amount:.2f}",
                "currency_code": currency,
            }
        },
        timeout=20,
    )

    r.raise_for_status()
    return r.json()["id"]


def send_deposit_refund(
    *,
    db: Session,
    booking: Booking,
    amount: float,
) -> str:
    if amount <= 0:
        raise ValueError("Refund amount must be > 0")

    if booking.payment_method != "paypal":
        raise RuntimeError("Refund supported only for PayPal")

    if not booking.deposit_capture_id:
        raise RuntimeError("Missing PayPal DEPOSIT capture ID")

    refund_id = paypal_refund_capture(
        capture_id=booking.deposit_capture_id,
        amount=amount,
        currency=(booking.currency or "CAD"),
    )

    booking.deposit_refund_amount = amount
    booking.deposit_refund_sent = True
    booking.deposit_refund_sent_at = datetime.utcnow()

    db.commit()
    return refund_id
