# app/webhooks.py
import os, stripe
from fastapi import APIRouter, Request, HTTPException
from .database import SessionLocal
from .models import Booking

router = APIRouter()

# مفتاح Stripe السري من المتغيرات (بدون ما يطيّح السيرفر لو مفقود)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

@router.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    wh_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not wh_secret:
        # خلي الخطأ واضح في اللوج بدل كراش أثناء الإقلاع
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET not set")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, wh_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    etype = event.get("type")
    print("Webhook event:", etype)

    # لو كنت ترسل booking_id في metadata عند إنشاء الـ PaymentIntent
    if etype in ("payment_intent.succeeded", "payment_intent.payment_failed"):
        pi = event["data"]["object"]
        meta = pi.get("metadata") or {}
        booking_id = meta.get("booking_id")
        if booking_id:
            db = SessionLocal()
            try:
                b = db.get(Booking, int(booking_id))
                if b:
                    if etype == "payment_intent.succeeded":
                        b.payment_status = "paid"
                    else:
                        if b.payment_status != "paid":
                            b.payment_status = "failed"
                    db.commit()
            finally:
                db.close()

    return {"ok": True}
