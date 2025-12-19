from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime, date, timedelta
import os

from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from .database import get_db
from .models import User, Item, Booking, UserReview
from .utils import category_label, display_currency, fx_convert
from .notifications_api import push_notification, notify_admins
from .pay_api import paypal_start, paypal_return

# ✅ ADDITIONS
from .utili_geo import locate_from_session
from .utili_tax import compute_order_taxes


router = APIRouter(tags=["bookings"])

DISPUTE_WINDOW_HOURS = 48
RENTER_REPLY_WINDOW_HOURS = 48

# =====================================================
# Auth helpers
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

def is_renter(user: User, bk: Booking) -> bool:
    return user.id == bk.renter_id

def is_owner(user: User, bk: Booking) -> bool:
    return user.id == bk.owner_id

def redirect_to_flow(bk: Booking):
    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)



# =====================================================
# Create booking
# =====================================================
@router.post("/bookings")
async def create_booking(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)

    form = await request.form()

    item_id_raw = form.get("item_id")
    start_raw   = form.get("start_date")
    end_raw     = form.get("end_date")

    if not item_id_raw or not start_raw or not end_raw:
        raise HTTPException(status_code=400, detail="Missing booking data")

    try:
        item_id    = int(item_id_raw)
        start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
        end_date   = datetime.strptime(end_raw, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking data")

    if end_date <= start_date:
        raise HTTPException(status_code=400, detail="Invalid dates")

    item = db.get(Item, item_id)
    if not item or item.owner_id == user.id:
        raise HTTPException(status_code=400, detail="Invalid item")

    days = max(1, (end_date - start_date).days)
    total_amount = days * item.price_per_day

    bk = Booking(
        item_id=item.id,
        renter_id=user.id,
        owner_id=item.owner_id,
        start_date=start_date,
        end_date=end_date,
        days=days,
        price_per_day_snapshot=item.price_per_day,
        total_amount=total_amount,
        status="requested",

        payment_provider="paypal",
        payment_status="pending",
        online_status="created",

        platform_fee=0,
        rent_amount=total_amount,
        hold_deposit_amount=0,
        owner_payout_amount=0,
        deposit_amount=0,
        deposit_charged_amount=0,
        amount_native=total_amount,
        amount_display=total_amount,
        amount_paid_cents=0,

        rent_paid=False,
        security_paid=False,
        security_amount=0,
        security_status="not_paid",
        refund_done=False,
        payout_executed=False,
        owner_due_amount=0,

        timeline_created_at=datetime.utcnow(),
    )

    db.add(bk)
    db.commit()
    db.refresh(bk)

    push_notification(
        db,
        bk.owner_id,
        "New booking request",
        f"Request on '{item.title}'.",
        f"/bookings/flow/{bk.id}",
        "booking",
    )

    return redirect_to_flow(bk)  

# =====================================================
# Booking flow page  ✅ FIX: GEO ONLY FOR RENTER
# =====================================================
@router.get("/bookings/flow/{booking_id}")
def booking_flow(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    item = db.get(Item, bk.item_id)
    owner = db.get(User, bk.owner_id)
    renter = db.get(User, bk.renter_id)

    # ===============================
    # GEO CHECK: ONLY FOR RENTER
    # ===============================
    geo = locate_from_session(request)
    country = (geo.get("country") or "").upper() if isinstance(geo, dict) else ""
    region  = (geo.get("region") or "").upper() if isinstance(geo, dict) else ""

    # ✅ إذا كان OWNER: لا نطلب Geo نهائيًا
    if is_owner(user, bk):
        # نترك geo كما هو للعرض فقط (إن وُجد)، لكن لا نعمل redirect أبداً
        pass
    else:
        # ✅ إذا كان RENTER: Geo إجباري للضرائب والدفع
        if not country:
            return RedirectResponse(
                url=f"/geo/pick?next=/bookings/flow/{bk.id}",
                status_code=303
            )

        # ✅ المقاطعة/الولاية مطلوبة فقط لـ CA و US
        if country in ("CA", "US") and not region:
            return RedirectResponse(
                url=f"/geo/pick?next=/bookings/flow/{bk.id}",
                status_code=303
            )

    # ===============================
    # ORDER SUMMARY
    # ===============================
    rent = bk.total_amount
    sevor_fee = round(rent * 0.01, 2)

    tax_lines = []
    tax_total = 0

    # ✅ الضرائب تُحسب فقط للـ RENTER (لأنه هو الذي سيدفع)
    if is_owner(user, bk):
        processing_fee = 0
        grand_total = round(rent + sevor_fee, 2)
    else:
        tax_base = rent + sevor_fee

        tax_result = compute_order_taxes(
            subtotal=tax_base,
            geo={
                "country": country,
                "sub": region,
            }
        )

        tax_lines = tax_result.get("lines", [])
        tax_total = tax_result.get("total", 0)
        processing_fee = round(rent * 0.029 + 0.30, 2)

        grand_total = round(
            rent + sevor_fee + tax_total + processing_fee,
            2
        )

    renter_reviews_count = 0
    renter_reviews_avg = 0.0
    if renter:
        q = db.query(UserReview).filter(UserReview.target_user_id == renter.id)
        renter_reviews_count = q.count()
        if renter_reviews_count:
            avg = db.query(func.avg(UserReview.stars)).filter(
                UserReview.target_user_id == renter.id
            ).scalar()
            renter_reviews_avg = round(float(avg or 0), 1)

    ctx = {
        "request": request,
        "booking": bk,
        "item": item,
        "owner": owner,
        "renter": renter,
        "is_owner": is_owner(user, bk),
        "is_renter": is_renter(user, bk),
        "category_label": category_label,
        "renter_reviews_count": renter_reviews_count,
        "renter_reviews_avg": renter_reviews_avg,
        "dispute_window_hours": DISPUTE_WINDOW_HOURS,
        "session_user": request.session.get("user"),

        # PRICING
        "rent": rent,
        "sevor_fee": sevor_fee,
        "tax_lines": tax_lines,
        "tax_total": tax_total,
        "processing_fee": processing_fee,
        "grand_total": grand_total,
        "geo": geo,
        "geo_country": country,
        "geo_region": region,
    }

    return request.app.templates.TemplateResponse("booking_flow.html", ctx)

# =====================================================
# Owner decision
# =====================================================
@router.post("/bookings/{booking_id}/owner/decision")
def owner_decision_route(
    booking_id: int,
    decision: Literal["accepted", "rejected"] = Form(...),
    deposit_amount: float = Form(0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403)

    if decision == "rejected":
        bk.status = "rejected"
        bk.rejected_at = datetime.utcnow()
        db.commit()
        return redirect_to_flow(bk)

    bk.status = "accepted"
    bk.accepted_at = datetime.utcnow()
    bk.security_amount = deposit_amount
    bk.deposit_amount = int(deposit_amount)
    bk.hold_deposit_amount = int(deposit_amount)

    db.commit()
    db.refresh(bk)

    push_notification(
        db,
        bk.renter_id,
        "Booking accepted",
        "Please complete payment via PayPal.",
        f"/bookings/flow/{bk.id}",
        "booking",
    )

    return redirect_to_flow(bk)

# =====================================================
# Pickup
# =====================================================
@router.post("/bookings/{booking_id}/pickup")
def renter_pickup(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403)

    if bk.status != "paid":
        raise HTTPException(status_code=400)

    bk.status = "picked_up"
    bk.picked_up_at = datetime.utcnow()
    db.commit()

    return redirect_to_flow(bk)

# =====================================================
# Return
# =====================================================
@router.post("/bookings/{booking_id}/return")
def renter_return(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403)

    bk.status = "returned"
    bk.returned_at = datetime.utcnow()
    db.commit()

    notify_admins(
        db,
        "Deposit review required",
        f"Booking #{bk.id} requires deposit decision.",
        f"/bookings/flow/{bk.id}",
    )

    return redirect_to_flow(bk)

# =====================================================
# Booking index
# =====================================================
@router.get("/bookings")
def bookings_index(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    view: Literal["renter", "owner"] = "renter",
):
    require_auth(user)

    if view == "owner":
        bookings = db.query(Booking).filter(Booking.owner_id == user.id).all()
    else:
        bookings = db.query(Booking).filter(Booking.renter_id == user.id).all()

    return request.app.templates.TemplateResponse(
        "booking_index.html",
        {
            "request": request,
            "bookings": bookings,
            "view": view,
            "user": user,
        },
    )

# ========================================
# UI: Create page
# ========================================
@router.get("/bookings/new")
def booking_new_page(
    request: Request,
    item_id: int = Query(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)

    item = db.get(Item, item_id)
    if not item or item.is_active != "yes":
        raise HTTPException(status_code=404, detail="Item not available")

    item_cur = (item.currency or "CAD").upper()
    disp_cur = display_currency(request)

    today = date.today()
    ctx = {
        "request": request,
        "user": user,
        "session_user": request.session.get("user"),
        "display_currency": disp_cur,
        "item": item,
        "disp_price": item.price_per_day,
        "item_currency": item_cur,
        "start_default": today,
        "end_default": today + timedelta(days=1),
        "days_default": 1,
    }

    return request.app.templates.TemplateResponse("booking_new.html", ctx)
