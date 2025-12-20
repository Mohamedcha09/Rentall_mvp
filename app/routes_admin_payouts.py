from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, User, UserPayoutMethod

router = APIRouter(prefix="/admin", tags=["admin-payouts"])

# =====================================================
# Helpers
# =====================================================
def get_current_user(request: Request, db: Session) -> User | None:
    sess = request.session.get("user")
    if not sess:
        return None
    return db.query(User).get(sess.get("id"))

def require_admin(user: User):
    if not user or not user.is_super_admin:
        raise HTTPException(status_code=403, detail="Admin only")


# =====================================================
# GET – Admin payouts page
# =====================================================
@router.get("/payouts", response_class=HTMLResponse)
def admin_payouts(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    bookings = (
        db.query(Booking)
        .filter(
                Booking.payout_ready == True,
                Booking.payout_sent == False,
                Booking.status == "completed")
        .order_by(Booking.updated_at.asc())
        .all()
    )

    rows = []
    for b in bookings:
        payout = (
            db.query(UserPayoutMethod)
            .filter(
                UserPayoutMethod.user_id == b.owner_id,
                UserPayoutMethod.is_active == True
            )
            .first()
        )

        rows.append({
            "booking": b,
            "owner": b.owner,
            "payout": payout
        })

    return request.app.templates.TemplateResponse(
        "admin_payouts.html",
        {
            "request": request,
            "user": user,
            "rows": rows
        }
    )


# =====================================================
# POST – Mark payout as sent
# =====================================================
@router.post("/payouts/{booking_id}/mark-sent")
def mark_payout_sent(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    require_admin(user)

    booking = db.query(Booking).get(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.payout_sent = True
    booking.payout_ready = False
    booking.payout_sent_at = db.execute("SELECT NOW()").scalar()

    db.commit()

    return RedirectResponse("/admin/payouts", status_code=303)
