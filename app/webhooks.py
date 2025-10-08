# app/webhooks.py
import os, stripe
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        return JSONResponse({"error": "Missing STRIPE_WEBHOOK_SECRET"}, status_code=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    print("✅ Webhook received:", event["type"])
    return {"received": True}