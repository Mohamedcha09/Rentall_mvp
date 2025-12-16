# app/webhooks.py
import os
import httpx
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking

router = APIRouter(tags=["paypal-webhook"])

# =========================
# PayPal Config
# =========================
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox | live
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET")

BASE_URL = (
    "https://api-m.paypal.com"
    if PAYPAL_MODE == "live"
    else "https://api-m.sandbox.paypal.com"
)

# =========================
# Helpers
# =========================
class PayPalWebhookError(Exception):
    pass


async def _get_access_token() -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/v1/oauth2/token",
            auth=httpx.BasicAuth(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
            data={"grant_type": "client_credentials"},
        )
    if r.status_code != 200:
        raise PayPalWebhookError(r.text)
    return r.json()["access_token"]


async def verify_webhook(headers, body: bytes) -> bool:
    """
    Verify PayPal webhook signature
    """
    token = await _get_access_token()

    payload = {
        "auth_algo": headers.get("paypal-auth-algo"),
        "cert_url": headers.get("paypal-cert-url"),
        "transmission_id": headers.get("paypal-transmission-id"),
        "transmission_sig": headers.get("paypal-transmission-sig"),
        "transmission_time": headers.get("paypal-transmission-time"),
        "webhook_id": PAYPAL_WEBHOOK_ID,
        "webhook_event": body.decode(),
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/v1/notifications/verify-webhook-signature",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

    return r.json().get("verification_status") == "SUCCESS"


# =========================
# Webhook Endpoint
# =========================
@router.post("/paypal/webhook")
async def paypal_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    body = await request.body()

    # 1️⃣ Verify webhook
    verified = await verify_webhook(request.headers, body)
    if not verified:
        raise HTTPException(status_code=400, detail="Invalid PayPal webhook")

    event = await request.json()
    event_type = event.get("event_type")

    # =====================================================
    # 2️⃣ ORDER APPROVED (user finished PayPal checkout)
    # =====================================================
    if event_type == "CHECKOUT.ORDER.APPROVED":
        order_id = event["resource"]["id"]

        booking = db.query(Booking).filter(
            Booking.paypal_order_id == order_id
        ).first()

        if booking:
            booking.payment_status = "approved"
            db.commit()

    # =====================================================
    # 3️⃣ PAYMENT CAPTURED (money received)
    # =====================================================
    elif event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = event["resource"]
        capture_id = resource["id"]
        order_id = resource["supplementary_data"]["related_ids"]["order_id"]

        booking = db.query(Booking).filter(
            Booking.paypal_order_id == order_id
        ).first()

        # ⛔ protection against duplicate webhooks
        if booking and booking.payment_status != "paid":
            booking.payment_status = "paid"
            booking.status = "paid"
            booking.paypal_capture_id = capture_id
            booking.timeline_paid_at = datetime.utcnow()
            db.commit()

    return {"status": "ok"}
