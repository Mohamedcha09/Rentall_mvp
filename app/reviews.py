# app/reviews.py
from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi.templating import Jinja2Templates

from .database import get_db
from .models import Booking, ItemReview, UserReview
from .utils import display_currency

router = APIRouter(prefix="/reviews", tags=["reviews"])
templates = Jinja2Templates(directory="app/templates")


def _require_login(request: Request):
    u = (request.session or {}).get("user")
    if not u:
        raise HTTPException(status_code=401, detail="not logged in")
    return u


def _int(v, d=0):
    try:
        return int(v)
    except Exception:
        return d


# =============== Renter rating page (GET) ===============
@router.get("/renter/{booking_id}")
def renter_rate_page(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    u = _require_login(request)
    bk: Booking | None = db.query(Booking).filter(Booking.id == booking_id).first()
    if not bk:
        raise HTTPException(status_code=404, detail="booking not found")
    if bk.renter_id != u["id"]:
        raise HTTPException(status_code=403, detail="not your booking")

    return templates.TemplateResponse(
        "reviews_renter.html",
        {
            "request": request,
            "title": f"Rate booking #{bk.id}",
            "booking": bk,
            "display_currency": display_currency,
            "session_user": request.session.get("user"),
        },
    )


# =============== 1) Renter rates the item + mark as (returned) ===============
@router.post("/renter/{booking_id}")
def renter_rates_item(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    rating: int = Form(...),
    comment: str = Form(""),
):
    u = _require_login(request)

    bk: Booking | None = db.query(Booking).filter(Booking.id == booking_id).first()
    if not bk:
        raise HTTPException(status_code=404, detail="booking not found")
    if bk.renter_id != u["id"]:
        raise HTTPException(status_code=403, detail="not your booking")

    # Prevent duplicate rating for the same booking by the same renter
    exists = db.query(ItemReview).filter(
        and_(ItemReview.booking_id == bk.id, ItemReview.rater_id == u["id"])
    ).first()
    if exists:
        # ✳️ Do not go to the listing page; return directly to the booking page
        return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

    stars = max(1, min(5, _int(rating, 5)))
    ir = ItemReview(
        booking_id=bk.id,
        item_id=bk.item_id,
        rater_id=u["id"],
        stars=stars,
        comment=(comment or "").strip() or None,
    )
    db.add(ir)

    # Mark "returned"
    if not bk.returned_at:
        bk.returned_at = datetime.utcnow()
    if bk.status not in ("returned", "in_review", "completed", "closed"):
        bk.status = "returned"

    db.commit()

    # ✳️ After saving, send the user back to the booking page (not the listing page)
    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)


# =============== 2) Owner rates the renter ===============
@router.post("/owner/{booking_id}")
def owner_rates_renter(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    rating: int = Form(...),
    comment: str = Form(""),
):
    u = _require_login(request)

    bk: Booking | None = db.query(Booking).filter(Booking.id == booking_id).first()
    if not bk:
        raise HTTPException(status_code=404, detail="booking not found")
    if bk.owner_id != u["id"]:
        raise HTTPException(status_code=403, detail="not your booking")

    exists = db.query(UserReview).filter(
        and_(
            UserReview.booking_id == bk.id,
            UserReview.owner_id == u["id"],
            UserReview.target_user_id == bk.renter_id,
        )
    ).first()
    if exists:
        return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

    stars = max(1, min(5, _int(rating, 5)))
    ur = UserReview(
        booking_id=bk.id,
        owner_id=u["id"],
        target_user_id=bk.renter_id,
        stars=stars,
        comment=(comment or "").strip() or None,
    )
    db.add(ur)
    db.commit()
    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)
