from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, User
from .pay_api import create_paypal_order, capture_paypal_order, PayPalError

router = APIRouter(tags=["paypal"])


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None


@router.post("/api/paypal/checkout/rent/{booking_id}")
async def paypal_checkout_rent(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay")

    amount = float(bk.total_amount or bk.rent_amount or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    base = str(request.base_url).rstrip("/")
    return_url = f"{base}/paypal/return/{bk.id}"
    cancel_url = f"{base}/bookings/flow/{bk.id}"

    try:
        order = await create_paypal_order(
            amount=amount,
            currency=(bk.currency_paid or "CAD"),
            return_url=return_url,
            cancel_url=cancel_url,
            reference_id=f"booking_{bk.id}",
            description=f"Rent payment for booking #{bk.id}",
            custom_id=str(user.id),
        )
    except PayPalError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # إذا هذه الأعمدة غير موجودة في Booking، سنضيفها لاحقًا في models.py
    bk.payment_provider = "paypal"
    bk.paypal_order_id = order["order_id"]
    bk.payment_status = "pending"
    db.commit()

    return RedirectResponse(url=order["approval_url"], status_code=303)


@router.get("/paypal/return/{booking_id}")
async def paypal_return(
    booking_id: int,
    db: Session = Depends(get_db),
):
    bk = db.get(Booking, booking_id)
    if not bk or not getattr(bk, "paypal_order_id", None):
        raise HTTPException(status_code=404, detail="Booking not found")

    try:
        cap = await capture_paypal_order(bk.paypal_order_id)
    except PayPalError as e:
        raise HTTPException(status_code=400, detail=str(e))

    bk.paypal_capture_id = cap.get("capture_id")
    bk.payment_status = "paid"
    db.commit()

    return RedirectResponse(url=f"/bookings/flow/{bk.id}?paid=1", status_code=303)
