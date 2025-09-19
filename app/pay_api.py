# app/pay_api.py
import os, math, stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import Booking, User

router = APIRouter(prefix="/api/pay", tags=["payments"])

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
CURRENCY = os.getenv("CURRENCY", "eur")
PLATFORM_FEE_PCT = float(os.getenv("PLATFORM_FEE_PCT", "10"))

def to_cents(amount: int | float) -> int:
    return int(math.floor(float(amount) * 100))

@router.get("/config")
def config():
    return {
        "publishableKey": os.getenv("STRIPE_PUBLISHABLE_KEY", ""),
        "currency": CURRENCY
    }

@router.post("/intent/{booking_id}")
def create_intent(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(Booking).get(booking_id)
    if not b:
        raise HTTPException(404, "Booking not found")
    if b.payment_status in ("paid", "requires_capture"):
        return {"alreadyPaid": True}

    intent = stripe.PaymentIntent.create(
        amount=to_cents(b.total_amount),
        currency=CURRENCY,
        automatic_payment_methods={"enabled": True},
        metadata={"booking_id": str(b.id)},
    )
    b.payment_intent_id = intent.id
    b.payment_status = "requires_payment"
    db.commit()
    return {"clientSecret": intent.client_secret}

@router.post("/refund/{booking_id}")
def refund(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(Booking).get(booking_id)
    if not b or b.payment_status != "paid":
        raise HTTPException(400, "Booking not paid or not found")
    r = stripe.Refund.create(payment_intent=b.payment_intent_id)
    b.payment_status = "refunded"
    b.status = "cancelled"
    db.commit()
    return {"refund_id": r.id}

@router.post("/transfer/{booking_id}")
def transfer(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(Booking).get(booking_id)
    if not b or b.payment_status != "paid":
        raise HTTPException(400, "Booking not paid or not found")

    pi = stripe.PaymentIntent.retrieve(b.payment_intent_id)
    if not pi.charges.data:
        raise HTTPException(400, "No charge found")
    charge_id = pi.charges.data[0].id

    owner = db.query(User).get(b.owner_id)
    platform_fee = int(to_cents(b.total_amount) * (PLATFORM_FEE_PCT / 100.0))
    owner_amount = to_cents(b.total_amount) - platform_fee
    if owner_amount <= 0:
        raise HTTPException(400, "Owner amount invalid")

    if owner and owner.stripe_account_id:
        tr = stripe.Transfer.create(
            amount=owner_amount,
            currency=CURRENCY,
            destination=owner.stripe_account_id,
            source_transaction=charge_id,
            metadata={"booking_id": str(b.id)}
        )
        b.status = "active"
        db.commit()
        return {"transfer_id": tr.id, "owner_amount": owner_amount, "platform_fee": platform_fee}
    else:
        b.status = "active"
        db.commit()
        return {"warning": "Owner has no Stripe account; funds stay in platform balance."}

@router.post("/webhook/stripe")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature")
    wh_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, wh_secret) if wh_secret else None
        if not event:
            return JSONResponse({"received": True})
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")

    et = event["type"]
    data = event["data"]["object"]

    if et == "payment_intent.succeeded":
        pi_id = data["id"]
        b = db.query(Booking).filter(Booking.payment_intent_id == pi_id).first()
        if b:
            b.payment_status = "paid"
            b.status = "paid"
            db.commit()
    elif et in ("payment_intent.payment_failed", "payment_intent.canceled"):
        pi_id = data["id"]
        b = db.query(Booking).filter(Booking.payment_intent_id == pi_id).first()
        if b:
            b.payment_status = "failed"
            b.status = "cancelled"
            db.commit()

    return JSONResponse({"received": True})
