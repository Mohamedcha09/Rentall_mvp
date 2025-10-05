# app/routes_bookings.py
from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Item, Booking

router = APIRouter(tags=["bookings"])

# ======================================================
# Helpers
# ======================================================
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    if not uid:
        return None
    return db.get(User, uid)

def require_auth(user: Optional[User]):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

def require_booking(db: Session, booking_id: int) -> Booking:
    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    return bk

def is_renter(user: User, bk: Booking) -> bool:
    return user and user.id == bk.renter_id

def is_owner(user: User, bk: Booking) -> bool:
    return user and user.id == bk.owner_id

def redirect_to_flow(booking_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"/bookings/flow/{booking_id}", status_code=303)


# ======================================================
# صفحة إنشاء الحجز (يصلها المستخدم من "احجز الآن")
# ======================================================
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

    # تواريخ افتراضية
    today = date.today()
    tomorrow = today + timedelta(days=1)

    ctx = {
        "request": request,
        "title": "اختيار مدة الحجز",
        "session_user": request.session.get("user"),
        "item": item,
        "start_default": today.isoformat(),
        "end_default": tomorrow.isoformat(),
        "days_default": 1,
    }
    return request.app.templates.TemplateResponse("booking_new.html", ctx)


# ======================================================
# إنشاء حجز فعلي (من الفورم في booking_new.html)
# - ندعم /bookings و /bookings/create (alias) حتى يعمل الكود القديم والجديد
# ======================================================
def _create_booking_core(
    *,
    db: Session,
    user: User,
    item_id: int,
    start_date: str,
    end_date: str,
    days: int,
) -> Booking:
    item = db.get(Item, item_id)
    if not item or item.is_active != "yes":
        raise HTTPException(status_code=404, detail="Item not available")

    if item.owner_id == user.id:
        raise HTTPException(status_code=400, detail="Owner cannot book own item")

    price_per_day = item.price_per_day or 0
    total_amount = max(1, int(days)) * max(0, int(price_per_day))

    bk = Booking(
        item_id=item.id,
        renter_id=user.id,
        owner_id=item.owner_id,
        start_date=start_date,
        end_date=end_date,
        days=int(days),
        price_per_day_snapshot=price_per_day,
        total_amount=total_amount,

        # الحالة الأولية
        status="requested",

        # حقول الدفع/الديبو الأولية
        owner_decision=None,          # "accepted" | "rejected" | None (اختياري إن كانت موجودة في المودل)
        payment_method=None,          # "online" | "cash" | None
        payment_status="unpaid",      # "unpaid" | "paid" | "released"
        deposit_amount=0,             # يضبطه المالك لاحقًا إن أراد
        deposit_status=None,          # None | "held" | "partially_withheld" | "refunded"
        deposit_hold_id=None,         # لاحقًا مع Stripe

        # التايملاين
        timeline_created_at=datetime.utcnow(),
    )
    db.add(bk)
    db.commit()
    db.refresh(bk)
    return bk

@router.post("/bookings")
def create_booking(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),

    item_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    days: int = Form(...),
):
    require_auth(user)
    bk = _create_booking_core(
        db=db, user=user,
        item_id=item_id, start_date=start_date, end_date=end_date, days=days
    )
    return redirect_to_flow(bk.id)

# alias لدعم النماذج القديمة التي ترسل إلى /bookings/create
@router.post("/bookings/create")
def create_booking_alias(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),

    item_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    days: int = Form(...),
):
    require_auth(user)
    bk = _create_booking_core(
        db=db, user=user,
        item_id=item_id, start_date=start_date, end_date=end_date, days=days
    )
    return redirect_to_flow(bk.id)


# ======================================================
# صفحة التدفق (تتغير حسب الحالة)
# ======================================================
@router.get("/bookings/flow/{booking_id}")
def booking_flow_page(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if not (is_renter(user, bk) or is_owner(user, bk)):
        raise HTTPException(status_code=403, detail="Forbidden")

    item = db.get(Item, bk.item_id)
    owner = db.get(User, bk.owner_id)
    renter = db.get(User, bk.renter_id)

    ctx = {
        "request": request,
        "title": f"الحجز #{bk.id}",
        "session_user": request.session.get("user"),
        "booking": bk,
        "item": item,
        "owner": owner,
        "renter": renter,

        "i_am_owner": is_owner(user, bk),
        "i_am_renter": is_renter(user, bk),

        # فلاتر حالة جاهزة للواجهة
        "is_requested": (bk.status == "requested"),
        "is_declined": (bk.status == "declined"),
        "is_pending_payment": (bk.status == "pending_payment"),
        "is_awaiting_pickup": (bk.status == "awaiting_pickup"),
        "is_in_use": (bk.status == "in_use"),
        "is_awaiting_return": (bk.status == "awaiting_return"),
        "is_in_review": (bk.status == "in_review"),
        "is_completed": (bk.status == "completed"),
    }

    return request.app.templates.TemplateResponse("booking_flow.html", ctx)


# ======================================================
# قرار المالك: قبول/رفض
# ======================================================
@router.post("/bookings/{booking_id}/owner/decision")
def owner_decision(
    booking_id: int,
    decision: Literal["accepted", "rejected"] = Form(...),
    deposit_amount: int = Form(0),
    request: Request | None = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can decide")

    if bk.status != "requested":
        raise HTTPException(status_code=400, detail="Invalid state")

    if decision == "rejected":
        bk.status = "declined"
        # إن كان لديك حقل owner_decision في المودل:
        try:
            bk.owner_decision = "rejected"
        except Exception:
            pass
        bk.timeline_owner_decided_at = datetime.utcnow()
        db.commit()
        return redirect_to_flow(bk.id)

    # accepted
    try:
        bk.owner_decision = "accepted"
    except Exception:
        pass
    bk.deposit_amount = max(0, int(deposit_amount or 0))
    bk.timeline_owner_decided_at = datetime.utcnow()
    bk.status = "pending_payment"  # بانتظار اختيار/تنفيذ الدفع من المستأجر
    db.commit()
    return redirect_to_flow(bk.id)


# ======================================================
# اختيار طريقة الدفع من المستأجر: cash أو online
# ======================================================
@router.post("/bookings/{booking_id}/renter/choose_payment")
def renter_choose_payment(
    booking_id: int,
    method: Literal["cash", "online"] = Form(...),
    request: Request | None = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter can choose")

    if bk.status != "pending_payment":
        raise HTTPException(status_code=400, detail="Invalid state")

    if method == "cash":
        bk.payment_method = "cash"
        bk.payment_status = "unpaid"        # سيدفع يدويًا عند الاستلام
        bk.status = "awaiting_pickup"       # ننتظر أن يستلم المستأجر الغرض
        bk.timeline_payment_method_chosen_at = datetime.utcnow()
        db.commit()
        return redirect_to_flow(bk.id)

    # أونلاين: سيدفع الآن (الإيجار + الديبو). التحويل للمالك يتم عند "تم الاستلام"
    bk.payment_method = "online"
    bk.timeline_payment_method_chosen_at = datetime.utcnow()
    db.commit()
    return redirect_to_flow(bk.id)


# ======================================================
# (أونلاين) تنفيذ الدفع الآن — placeholder لسترايب
# ======================================================
@router.post("/bookings/{booking_id}/renter/pay_online")
def renter_pay_online(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    هنا لاحقًا سننشئ PaymentIntent + Hold للديبو عبر Stripe.
    الآن: نحاكي الدفع بنجاح، وننتقل للحالة awaiting_pickup.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter can pay")

    if bk.payment_method != "online" or bk.status != "pending_payment":
        raise HTTPException(status_code=400, detail="Invalid state")

    # TODO: Stripe Integration
    bk.payment_status = "paid"
    if (bk.deposit_amount or 0) > 0:
        bk.deposit_status = "held"              # تم حجز الديبو
        bk.deposit_hold_id = "HOLD_SIMULATED"   # مؤقتًا

    bk.status = "awaiting_pickup"               # ينتظر أن يأخذ المستأجر الغرض من المالك
    bk.timeline_paid_at = datetime.utcnow()
    db.commit()

    return redirect_to_flow(bk.id)


# ======================================================
# “تم استلام الغرض” — يضغطها المستأجر عند الاستلام
# ======================================================
@router.post("/bookings/{booking_id}/renter/confirm_received")
def renter_confirm_received(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter can confirm")

    if bk.status != "awaiting_pickup":
        raise HTTPException(status_code=400, detail="Invalid state")

    # عند الاستلام:
    # - إن كانت أونلاين: نُحوِّل مبلغ الإيجار للمالك (Stripe transfer لاحقًا).
    if bk.payment_method == "online":
        bk.payment_status = "released"               # مبلغ الإيجار حُوِّل
        bk.timeline_rental_released_at = datetime.utcnow()

    bk.status = "in_use"                              # الغرض الآن مع المستأجر
    bk.timeline_renter_received_at = datetime.utcnow()
    db.commit()

    return redirect_to_flow(bk.id)


# ======================================================
# “تم إرجاع الغرض” — يضغطها المالك عند استلامه من المستأجر
# ======================================================
@router.post("/bookings/{booking_id}/owner/confirm_return")
def owner_confirm_return(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can confirm")

    if bk.status not in ("in_use", "awaiting_return"):
        raise HTTPException(status_code=400, detail="Invalid state")

    # بعد تأكيد الإرجاع، ندخل مرحلة مراجعة الديبو
    bk.status = "in_review"
    bk.timeline_owner_returned_at = datetime.utcnow()
    db.commit()

    return redirect_to_flow(bk.id)


# ======================================================
# قرار الديبو — المالك (إرجاع كامل/جزئي/كامل الحجز)
# ======================================================
@router.post("/bookings/{booking_id}/owner/deposit_action")
def owner_deposit_action(
    booking_id: int,
    action: Literal["refund_all", "withhold_partial", "withhold_all"] = Form(...),
    partial_amount: int = Form(0),
    note: str = Form(""),
    request: Request | None = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can decide deposit")

    if bk.status != "in_review":
        raise HTTPException(status_code=400, detail="Invalid state")

    dep = max(0, bk.deposit_amount or 0)
    if dep == 0:
        bk.status = "completed"
        bk.timeline_closed_at = datetime.utcnow()
        db.commit()
        return redirect_to_flow(bk.id)

    # TODO: Stripe actions (refund/capture)
    if action == "refund_all":
        bk.deposit_status = "refunded"
    elif action == "withhold_partial":
        amt = max(0, int(partial_amount or 0))
        if amt <= 0 or amt >= dep:
            raise HTTPException(status_code=400, detail="Invalid partial amount")
        bk.deposit_status = "partially_withheld"
    elif action == "withhold_all":
        bk.deposit_status = "partially_withheld"  # إبقاء تسمية موحّدة
    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    bk.status = "completed"
    bk.timeline_closed_at = datetime.utcnow()
    db.commit()

    return redirect_to_flow(bk.id)


# ======================================================
# اختصار: للمالك ليضع الحالة “بانتظار الاسترجاع” (اختياري)
# ======================================================
@router.post("/bookings/{booking_id}/owner/mark_wait_return")
def owner_mark_wait_return(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner")

    if bk.status != "in_use":
        raise HTTPException(status_code=400, detail="Invalid state")

    bk.status = "awaiting_return"
    db.commit()
    return redirect_to_flow(bk.id)


# ======================================================
# JSON صغير لإرجاع حالة الحجز (يفيد بالـ polling)
# ======================================================
@router.get("/api/bookings/{booking_id}/state")
def booking_state(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not (is_renter(user, bk) or is_owner(user, bk)):
        raise HTTPException(status_code=403, detail="Forbidden")

    return JSONResponse({
        "id": bk.id,
        "status": bk.status,
        "owner_decision": getattr(bk, "owner_decision", None),
        "payment_method": bk.payment_method,
        "payment_status": bk.payment_status,
        "deposit_amount": getattr(bk, "deposit_amount", 0),
        "deposit_status": getattr(bk, "deposit_status", None),
    })