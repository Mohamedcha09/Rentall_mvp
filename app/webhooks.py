# app/webhooks.py
# Webhooks temporarily disabled (Stripe removed)

from fastapi import APIRouter

router = APIRouter()

@router.get("/webhooks/ping")
def webhook_ping():
    """
    Health check endpoint.
    Webhooks are currently disabled.
    """
    return {
        "ok": True,
        "msg": "Webhooks disabled (Stripe removed, PayPal manual flow active)"
    }
