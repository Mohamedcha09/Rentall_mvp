# app/reviews.py
from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_

from .database import get_db
from .models import Booking, ItemReview, UserReview

router = APIRouter(prefix="/reviews", tags=["reviews"])

def _require_login(request: Request):
    u = (request.session or {}).get("user")
    if not u:
        raise HTTPException(status_code=401, detail="not logged in")
    return u

def _int(v, d=0):
    try: return int(v)
    except: return d

# =============== 1) المستأجر يقيّم العنصر + يعلّم "تم الإرجاع" ===============
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

    # لا تسمح بالتكرار لنفس الحجز من نفس المستأجر
    exists = db.query(ItemReview).filter(
        and_(ItemReview.booking_id == bk.id, ItemReview.rater_id == u["id"])
    ).first()
    if exists:
        # فقط ارجاع دون إنشاء
        return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

    stars = max(1, min(5, _int(rating, 5)))

    # أنشئ مراجعة العنصر
    ir = ItemReview(
        booking_id=bk.id,
        item_id=bk.item_id,
        rater_id=u["id"],
        stars=stars,
        comment=(comment or "").strip() or None,
    )
    db.add(ir)

    # علّم الحجز "تم الإرجاع" إن لم يكن معلماً
    if not bk.returned_at:
        bk.returned_at = datetime.utcnow()
    if bk.status not in ("returned", "in_review", "completed", "closed"):
        bk.status = "returned"

    db.commit()
    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)


# =============== 2) المالك يقيّم المستأجر (يظهر في بروفايل المستأجر) ===============
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

    # منع التكرار: تقييم واحد من نفس المالك لنفس المستأجر على نفس الحجز
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
