# =====================================================
# routes_admin_payouts.py
# =====================================================
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
front_router = APIRouter(prefix="/f", tags=["payouts-front"])

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
# GET – Pending payouts (RENT + DEPOSIT)
# =====================================================
@router.get("/payouts", response_class=HTMLResponse)
def admin_payouts(
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    rows = []

    # ==========================
    # RENT PAYOUTS (PENDING)
    # ==========================
    rent_bookings = (
        db.query(Booking)
        .options(joinedload(Booking.owner))
        .filter(
            Booking.payout_ready == True,
            Booking.payout_sent == False,
        )
        .order_by(Booking.created_at.asc())
        .all()
    )

    for b in rent_bookings:
        payout = (
            db.query(UserPayoutMethod)
            .filter(
                UserPayoutMethod.user_id == b.owner_id,
                UserPayoutMethod.is_active == True,
            )
            .first()
        )

        rows.append({
            "type": "rent",
            "booking": b,
            "owner": b.owner,
            "amount": b.owner_amount,
            "currency": b.currency_display or b.currency,
            "payout": payout,
        })

    # ==========================
    # DEPOSIT COMPENSATIONS (PENDING ONLY)
    # ==========================
    deposit_bookings = (
        db.query(Booking)
        .options(joinedload(Booking.owner))
        .filter(
            Booking.dm_decision_amount > 0,
            Booking.deposit_comp_sent == False,
        )
        .order_by(Booking.created_at.asc())
        .all()
    )

    for b in deposit_bookings:
        payout = (
            db.query(UserPayoutMethod)
            .filter(
                UserPayoutMethod.user_id == b.owner_id,
                UserPayoutMethod.is_active == True,
            )
            .first()
        )

        # ==========================
        # DISPLAY ONLY LOGIC (DEPOSIT)
        # ==========================
        # deposit الأصلي الذي دفعه الزبون (مثال: 20)
        deposit_gross = float(getattr(b, "deposit_amount", 0) or 0)

        # ✅ PayPal fee محسوب من deposit الأصلي: 2.9% + 0.30
        # مثال: 20 => 20*0.029 + 0.30 = 0.88
        paypal_fee = round((deposit_gross * 0.029) + 0.30, 2)

        # قرار MD الاسمي (مثال: 10)
        md_amount = float(getattr(b, "dm_decision_amount", 0) or 0)

        # ✅ المبلغ الحقيقي الذي يمكن إرساله للمالك
        # (قرار MD − عمولة PayPal المحسوبة من deposit الأصلي)
        net_to_owner = round(md_amount - paypal_fee, 2)
        if net_to_owner < 0:
            net_to_owner = 0.0

        rows.append({
            "type": "deposit",
            "booking": b,
            "owner": b.owner,

            # ✅ هذا هو الرقم الذي سيظهر في بطاقة الأدمن
            "amount": net_to_owner,

            # معلومات إضافية (للعرض فقط)
            "md_amount": md_amount,
            "paypal_fee": paypal_fee,
            "deposit_gross": deposit_gross,

            "currency": b.currency_display or b.currency,
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
# POST – Mark RENT payout as sent
# =====================================================
@router.post("/payouts/{booking_id}/mark-sent")
def mark_rent_payout_sent(
    booking_id: int,
    request: Request,
    reference: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404)

    booking.payout_sent = True
    booking.payout_ready = False
    booking.payout_sent_at = datetime.utcnow()
    booking.payout_reference = reference
    db.commit()

    push_notification(
        db,
        booking.owner_id,
        "💸 Rent payout sent",
        f"Your rent payout of {booking.owner_amount} "
        f"{booking.currency_display or booking.currency} has been sent.",
        f"/f/payouts/receipt/{booking.id}",
        kind="payout",
    )

    return RedirectResponse("/admin/payouts", status_code=303)

# =====================================================
# POST – Mark DEPOSIT payout as sent
# =====================================================
@router.post("/payouts/{booking_id}/deposit/mark-sent")
def mark_deposit_payout_sent(
    booking_id: int,
    request: Request,
    reference: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404)

    if booking.dm_decision_amount <= 0:
        raise HTTPException(status_code=400, detail="No deposit compensation")

    # ✅ منع الإرسال مرتين
    if booking.deposit_comp_sent:
        return RedirectResponse("/admin/payouts", status_code=303)

    # ✅ تسجيل الإرسال
    booking.deposit_comp_sent = True
    booking.deposit_comp_sent_at = datetime.utcnow()
    booking.deposit_comp_reference = reference
    db.commit()

    push_notification(
        db,
        booking.owner_id,
        "🛡 Deposit compensation sent",
        f"You received {booking.dm_decision_amount} "
        f"{booking.currency_display or booking.currency} "
        "as a deposit compensation.",
        f"/f/payouts/deposit/{booking.id}",
        kind="deposit",
    )

    return RedirectResponse("/admin/payouts", status_code=303)

# =====================================================
# GET – Paid payouts history (RENT)
# =====================================================
@router.get("/payouts/paid", response_class=HTMLResponse)
def admin_payouts_paid(
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.owner))
        .filter(Booking.payout_sent == True)
        .order_by(Booking.payout_sent_at.asc())
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
        "admin_payouts_paid.html",
        {
            "request": request,
            "rows": rows,
            "session_user": request.session.get("user"),
        }
    )

# =====================================================
# GET – Payout receipt (OWNER – RENT)
# =====================================================
@front_router.get("/payouts/receipt/{booking_id}", response_class=HTMLResponse)
def payout_receipt_front(
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

# =====================================================
# GET – Deposit receipt (OWNER)
# =====================================================
@front_router.get("/payouts/deposit/{booking_id}", response_class=HTMLResponse)
def deposit_receipt_front(
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
            Booking.dm_decision_amount > 0,
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
        "deposit_receipt.html",
        {
            "request": request,
            "booking": booking,
            "payout": payout,
            "session_user": request.session.get("user"),
        }
    )

# =====================================================
# GET – Deposit payouts history (ADMIN)
# =====================================================
@router.get("/payouts/deposit/paid", response_class=HTMLResponse)
def admin_deposit_payouts_paid(
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.owner))
        .filter(
            Booking.dm_decision_amount > 0,
            Booking.deposit_comp_sent == True,
        )
        .order_by(Booking.deposit_comp_sent_at.asc())
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
            "amount": b.dm_decision_amount,
            "currency": b.currency_display or b.currency,
            "payout": payout,
        })

    return request.app.templates.TemplateResponse(
        "admin_deposit_payouts_paid.html",
        {
            "request": request,
            "rows": rows,
            "session_user": request.session.get("user"),
        }
    )
