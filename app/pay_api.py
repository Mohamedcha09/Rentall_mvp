# app/pay_api.py
import os
from decimal import Decimal

import stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, Item, User

router = APIRouter()

# مفتاح Stripe السري (من المتغيرات البيئية)
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

CURRENCY = os.getenv("CURRENCY", "cad")
PLATFORM_FEE_PCT = int(os.getenv("PLATFORM_FEE_PCT", "10"))

@router.post("/api/checkout/{booking_id}/intent")
def create_payment_intent(booking_id: int, request: Request, db: Session = Depends(get_db)):
    # لازم يكون المستخدم مسجّل دخول
    u = request.session.get("user")
    if not u:
        raise HTTPException(401, "يرجى تسجيل الدخول")

    booking = db.query(Booking).get(booking_id)
    if not booking:
        raise HTTPException(404, "الحجز غير موجود")
    if booking.status != "confirmed":
        raise HTTPException(400, "الحجز ليس مؤكدًا")

    item = db.query(Item).get(booking.item_id)
    if not item:
        raise HTTPException(404, "العنصر غير موجود")

    owner = db.query(User).get(item.owner_id)  # غيّرها لو اسم العمود مختلف عندك
    if not owner or not owner.stripe_account_id:
        raise HTTPException(400, "صاحب العنصر لم يفعّل Stripe Connect بعد")

    amount = int(Decimal(str(booking.total_amount)) * 100)     # إلى السنت
    app_fee = amount * PLATFORM_FEE_PCT // 100                 # عمولة المنصّة

    try:
        pi = stripe.PaymentIntent.create(
            amount=amount,
            currency=CURRENCY,
            automatic_payment_methods={"enabled": True},
            application_fee_amount=app_fee,
            transfer_data={"destination": owner.stripe_account_id},
            metadata={"booking_id": str(booking.id)},
        )
    except Exception as e:
        raise HTTPException(400, f"Stripe error: {str(e)}")

    return {"clientSecret": pi.client_secret}
