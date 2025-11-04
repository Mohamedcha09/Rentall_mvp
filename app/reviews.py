# app/reviews.py
from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi.templating import Jinja2Templates

from .database import get_db
from .models import Booking, ItemReview, UserReview

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


# =============== صفحة التقييم للمستأجر (GET) ===============
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
            "title": f"تقييم الحجز #{bk.id}",
            "booking": bk,
            "session_user": request.session.get("user"),
        },
    )


# =============== 1) المستأجر يقيّم العنصر + نعلّم (تم الإرجاع) ===============
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

    # منع تكرار تقييم نفس الحجز من نفس المستأجر
    exists = db.query(ItemReview).filter(
        and_(ItemReview.booking_id == bk.id, ItemReview.rater_id == u["id"])
    ).first()
    if exists:
        # ✳️ لا نذهب لصفحة المنشور، نرجع مباشرة لصفحة الحجز
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

    # تعليم "تم الإرجاع"
    if not bk.returned_at:
        bk.returned_at = datetime.utcnow()
    if bk.status not in ("returned", "in_review", "completed", "closed"):
        bk.status = "returned"

    db.commit()

    # ✳️ بعد الحفظ نرجّع المستخدم لصفحة الحجز (وليس صفحة المنشور)
    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)


# =============== 2) المالك يقيّم المستأجر ===============
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
