# app/webhooks.py
import os
import stripe
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .database import SessionLocal
# We will use the real handler from pay_api
from .pay_handlers import handle_checkout_completed

router = APIRouter()

@router.get("/stripe/webhook/ping")
def webhook_ping():
    """
    Quick check that the route is working (does not require a signature).
    """
    return {"ok": True, "msg": "stripe webhook endpoint is alive"}

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    This route receives Webhooks from Stripe (your endpoint is configured to it).
    After verifying the signature, we forward the event to the same handler used inside pay_api.py
    so the booking gets updated in the database, and the buttons disappear automatically.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        return JSONResponse({"error": "Missing STRIPE_WEBHOOK_SECRET"}, status_code=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # Useful diagnostic log
    try:
        print("✅ Webhook received:", event.get("type"))
    except Exception:
        pass

    # >>> The two most important lines: call the same real update logic
    if event.get("type") == "checkout.session.completed":
        session_obj = event["data"]["object"]
        db = SessionLocal()
        try:
            _handle_checkout_completed(session_obj, db)
        finally:
            db.close()

    return {"received": True}
