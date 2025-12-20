# app/checkout.py
import os
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Item, Booking

router = APIRouter()

# ===============================
# Payment page for a specific booking
# example: /checkout/123
# ===============================
@router.get("/checkout/{booking_id}", response_class=HTMLResponse)
def checkout_detail(booking_id: int, request: Request, db: Session = Depends(get_db)):
    # The user must be logged in
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    # Fetch booking + item + owner
    # Note: db.get is available in SQLAlchemy 2.x; if it doesn't work for you, use query.get
    booking = db.get(Booking, booking_id) if hasattr(db, "get") else db.query(Booking).get(booking_id)
    if not booking:
        # If the booking does not exist, redirect the user to the home page
        return RedirectResponse(url="/", status_code=303)

    item = db.get(Item, booking.item_id) if hasattr(db, "get") else db.query(Item).get(booking.item_id)
    owner = db.get(User, booking.owner_id) if hasattr(db, "get") else db.query(User).get(booking.owner_id)

    # Stripe publishable key for the client (Elements)
    pk = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    currency = (os.getenv("CURRENCY", "cad") or "cad").upper()


    # Render the template checkout_detail.html
    # This template calls /api/checkout/{booking_id}/intent from pay_api.py
    return request.app.templates.TemplateResponse(
        "checkout_detail.html",
        {
            "request": request,
            "title": f"Payment for booking #{booking.id}",
            "booking": booking,
            "item": item,
            "owner": owner,
            "pk": pk,
            "currency": currency,          # ⬅️ أضف هذا السطر
            "session_user": sess,  # for navbar
        },
    )

