from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
import csv
import io

from .database import get_db
from .models import Booking, User, UserPayoutMethod
from .notifications_api import push_notification

router = APIRouter(prefix="/admin", tags=["admin-payouts"])

# =====================================================
# Helpers
# =====================================================
def get_current_user(request: Request, db: Session) -> User | None:
    sess = request.session.get("user")
    if not sess:
        return None
    return db.get(User, sess.get("id"))

def require_admin(user: User | None):
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


# =====================================================
# GET – Pending payouts
# =====================================================
@router.get("/payouts", response_class=HTMLResponse)
def admin_payouts(
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.owner))
        .filter(
            Booking.payout_ready == True,
            Booking.payout_sent == False,
        )
        .order_by(Booking.updated_at.asc())
        .all()
    )

    rows = []
    for b in bookings:
        payout = (
            db.query(UserPayoutMethod)
            .filter(
                UserPayoutMethod.user_id == b.owner_id,
                UserPayoutMethod.is_active == True,
            )
            .first()
        )
        rows.append({
            "booking": b,
            "owner": b.owner,
            "payout": payout,
        })

    return request.app.templates.TemplateResponse(
        "admin_payouts.html",
        {
            "request": request,
            "user": user,
            "rows": rows,
            "session_user": request.session.get("user"),
        }
    )


# =====================================================
# POST – Mark payout as sent
# =====================================================
@router.post("/payouts/{booking_id}/mark-sent")
def mark_payout_sent(
    booking_id: int,
    request: Request,
    reference: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # ✅ تحديث الحالة
    booking.payout_sent = True
    booking.payout_ready = False
    booking.payout_sent_at = datetime.utcnow()
    booking.payout_reference = reference

    db.commit()

    # 🔔 إشعار + إيميل للمالك
    push_notification(
        db,
        booking.owner_id,
        "💸 Payout sent",
        f"Your payout of {booking.owner_amount} "
        f"{booking.currency_display or booking.currency} has been sent.",
        f"/bookings/flow/{booking.id}",
        kind="payout",
    )

    return RedirectResponse("/admin/payouts/paid", status_code=303)


# =====================================================
# GET – Paid payouts history
# =====================================================
@router.get("/payouts/paid", response_class=HTMLResponse)
def admin_payouts_paid(
    request: Request,
    db: Session = Depends(get_db),
    date_from: str | None = None,
    date_to: str | None = None,
    export: str | None = None,
):
    user = get_current_user(request, db)
    require_admin(user)

    q = (
        db.query(Booking)
        .options(joinedload(Booking.owner))
        .filter(Booking.payout_sent == True)
    )

    if date_from:
        q = q.filter(Booking.payout_sent_at >= date_from)
    if date_to:
        q = q.filter(Booking.payout_sent_at <= date_to)

    bookings = q.order_by(Booking.payout_sent_at.desc()).all()

    # ==========================
    # 📤 EXPORT CSV
    # ==========================
    if export == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Booking ID",
            "Owner",
            "Amount",
            "Currency",
            "Method",
            "Destination",
            "Paid at",
            "Reference",
        ])

        for b in bookings:
            payout = (
                db.query(UserPayoutMethod)
                .filter(
                    UserPayoutMethod.user_id == b.owner_id,
                    UserPayoutMethod.is_active == True,
                )
                .first()
            )

            writer.writerow([
                b.id,
                b.owner.full_name if b.owner else "",
                b.owner_amount,
                b.currency_display or b.currency,
                payout.method if payout else "",
                payout.destination if payout else "",
                b.payout_sent_at,
                getattr(b, "payout_reference", ""),
            ])

        output.seek(0)
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=payouts.csv"
            },
        )

    # ==========================
    # UI DATA
    # ==========================
    rows = []
    for b in bookings:
        payout = (
            db.query(UserPayoutMethod)
            .filter(
                UserPayoutMethod.user_id == b.owner_id,
                UserPayoutMethod.is_active == True,
            )
            .first()
        )
        rows.append({
            "booking": b,
            "owner": b.owner,
            "payout": payout,
        })

    return request.app.templates.TemplateResponse(
        "admin_payouts_paid.html",
        {
            "request": request,
            "rows": rows,
            "session_user": request.session.get("user"),
            "date_from": date_from,
            "date_to": date_to,
        }
    )

# =====================================================
# GET – Payout receipt (OWNER)
# =====================================================
@router.get("/payouts/receipt/{booking_id}", response_class=HTMLResponse)
def payout_receipt(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=403)

    booking = (
        db.query(Booking)
        .options(joinedload(Booking.owner))
        .filter(
            Booking.id == booking_id,
            Booking.owner_id == user.id,
            Booking.payout_sent == True,
        )
        .first()
    )

    if not booking:
        raise HTTPException(status_code=404)

    payout = (
        db.query(UserPayoutMethod)
        .filter(
            UserPayoutMethod.user_id == booking.owner_id,
            UserPayoutMethod.is_active == True
        )
        .first()
    )

    return request.app.templates.TemplateResponse(
        "payout_receipt.html",
        {
            "request": request,
            "booking": booking,
            "payout": payout,
            "session_user": request.session.get("user"),
        }
    )
