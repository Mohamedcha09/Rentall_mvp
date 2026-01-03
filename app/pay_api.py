# =====================================================
# pay_api.py — WALLET VERSION (FINAL)
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
from .models import (
    Booking,
    User,
    PlatformWallet,
    PlatformWalletLedger,
)

from .notifications_api import push_notification
from .utili_geo import locate_from_session
from .utili_tax import compute_order_taxes

router = APIRouter(tags=["payments"])

# =====================================================
# Helpers
# =====================================================

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


def flow_redirect(bk: Booking, flag: str):
    return RedirectResponse(
        url=f"/bookings/flow/{bk.id}?{flag}=1",
        status_code=303,
    )

# =====================================================
# PayPal core
# =====================================================

PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")
PAYPAL_BASE = "https://api-m.paypal.com" if PAYPAL_MODE == "live" else "https://api-m.sandbox.paypal.com"

def paypal_get_token() -> str:
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    secret = os.getenv("PAYPAL_CLIENT_SECRET")

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


def paypal_create_order(*, booking: Booking, amount: float, currency: str, pay_type: str) -> str:
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
                "return_url": f"https://sevor.net/paypal/return?booking_id={booking.id}&type={pay_type}",
                "cancel_url": f"https://sevor.net/bookings/flow/{booking.id}",
            },
        },
        timeout=20,
    )
    r.raise_for_status()

    for link in r.json().get("links", []):
        if link.get("rel") == "approve":
            return link["href"]

    raise RuntimeError("PayPal approval link not found")


def paypal_capture(order_id: str) -> dict:
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
# START PAYMENT
# =====================================================

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
        amount = float(bk.total_amount)
    else:
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
# RETURN + CAPTURE → WALLET
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

    data = paypal_capture(token)
    cap = data["purchase_units"][0]["payments"]["captures"][0]

    if (cap.get("status") or "").upper() != "COMPLETED":
        return flow_redirect(bk, "paypal_pending")

    payer = data.get("payer", {})
    bk.payer_email = payer.get("email_address")
    bk.payer_id = payer.get("payer_id")
    bk.payment_provider = "paypal"
    bk.payment_method = "paypal"

    currency = bk.currency or "CAD"
    wallet = db.query(PlatformWallet).filter_by(currency=currency).with_for_update().one()

    amount = float(bk.total_amount if type == "rent" else bk.security_amount)

    wallet.available_balance += amount

    db.add(PlatformWalletLedger(
        wallet_id=wallet.id,
        booking_id=bk.id,
        type="rent_in" if type == "rent" else "deposit_in",
        amount=amount,
        currency=currency,
        direction="in",
        source="paypal",
    ))

    if type == "rent":
        bk.rent_paid = True
        bk.payment_status = "paid"
    else:
        bk.security_paid = True
        bk.security_status = "held"
        bk.deposit_status = "held"

    if bk.rent_paid and (bk.security_paid or bk.security_amount == 0):
        bk.status = "paid"
        bk.timeline_paid_at = datetime.utcnow()

    db.commit()
    return flow_redirect(bk, "rent_ok" if type == "rent" else "security_ok")
