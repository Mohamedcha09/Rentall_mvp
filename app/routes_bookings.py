# app/routes_bookings.py
# ==============================================================
# صفحة/تدفّق الحجز في صفحة واحدة + إنشاء حجز من "احجز الآن"
# هذا الملف مُصحَّح بالكامل (أخطاء FastAPI/Request، 404، حساب الأيام...)
# ملاحظة مهمّة: لا تحذف شيئًا عند اللصق، فقط استبدل محتوى الملف كله بهذا الكود.
# ==============================================================

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
    """يجلب المستخدم من الجلسة أو يرجّع None."""
    data = request.session.get("user") or {}
    uid = data.get("id")
    if not uid:
        return None
    return db.get(User, uid)

def require_auth(user: Optional[User]):
    """يرفع 401 إن لم يكن المستخدم مسجّل الدخول."""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

def require_booking(db: Session, booking_id: int) -> Booking:
    """يجلب الحجز أو يرفع 404."""
    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    return bk

def is_renter(user: User, bk: Booking) -> bool:
    return bool(user) and user.id == bk.renter_id

def is_owner(user: User, bk: Booking) -> bool:
    return bool(user) and user.id == bk.owner_id

def redirect_to_flow(booking_id: int) -> RedirectResponse:
    """تحويل سريع لصفحة التدفق."""
    return RedirectResponse(url=f"/bookings/flow/{booking_id}", status_code=303)

def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def _compute_days(start_s: str, end_s: str) -> int:
    """يحسب عدد الأيام (بما لا يقل عن 1)."""
    try:
        sd = _parse_date(start_s)
        ed = _parse_date(end_s)
        delta = (ed - sd).days
        return max(1, delta)
    except Exception:
        return 1


# ======================================================
# إنشاء حجز (الصفحة التي يذهب لها زر "احجز الآن")
# ======================================================
@router.get("/bookings/new")
def booking_new_page(
    request: Request,
    item_id: int = Query(..., description="معرّف العنصر المراد حجزه"),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    صفحة اختيار المدة وطريقة الدفع المبدئية.
    """
    require_auth(user)

    item = db.get(Item, item_id)
    if not item or item.is_active != "yes":
        raise HTTPException(status_code=404, detail="Item not available")

    # تواريخ افتراضية (اليوم ← غدًا)
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
# إنشاء الحجز (POST من نموذج booking_new.html)
# ======================================================
@router.post("/bookings")
def create_booking(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),

    item_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    # قد لا يرسل الفرونت days؛ نحسبه إن لم يصل:
    days: Optional[int] = Form(None),
    # طريقة الدفع المبدئية من النموذج (لا تغيّر الحالة النهائية الآن)
    pay_method: Optional[Literal["online", "cash"]] = Form(None),
):
    """
    ينشئ طلب حجز بالحالة requested ثم يحوّل مباشرة لصفحة التدفق الواحدة.
    """
    require_auth(user)

    item = db.get(Item, item_id)
    if not item or item.is_active != "yes":
        raise HTTPException(status_code=404, detail="Item not available")

    # منع حجز صاحب الغرض لنفسه
    if item.owner_id == user.id:
        raise HTTPException(status_code=400, detail="Owner cannot book own item")

    # التحقق من التواريخ + حساب الأيام
    try:
        sd = _parse_date(start_date)
        ed = _parse_date(end_date)
        if ed <= sd:
            raise ValueError("end <= start")
    except Exception:
        # ارجع لصفحة new مع رسالة خطأ بسيطة
        return RedirectResponse(
            url=f"/bookings/new?item_id={item_id}&err=dates",
            status_code=303,
        )

    if not days or days < 1:
        days = (ed - sd).days
        days = max(1, days)

    # إعداد مبالغ مبدئية (لقطة للسعر اليومي)
    price_per_day = item.price_per_day or 0
    total_amount = max(1, days) * max(0, price_per_day)

    bk = Booking(
        item_id=item.id,
        renter_id=user.id,
        owner_id=item.owner_id,
        start_date=sd,
        end_date=ed,
        days=days,
        price_per_day_snapshot=price_per_day,
        total_amount=total_amount,

        # حالة أولية
        status="requested",

        # قرارات/وسائل الدفع
        owner_decision=None,                  # "accepted" | "rejected" | None
        payment_method=None,                  # "online" | "cash" | None
        payment_status="unpaid",              # "unpaid" | "paid" | "released"
        deposit_amount=0,                     # يحدده المالك عند القبول (إن أراد)
        deposit_status=None,                  # None | "held" | "partially_withheld" | "refunded"
        deposit_hold_id=None,                 # لحجز الديبو (Stripe لاحقًا)

        # تايملاين
        timeline_created_at=datetime.utcnow(),
    )

    db.add(bk)
    db.commit()
    db.refresh(bk)

    # تلميح: لا نثبت طريقة الدفع هنا؛ نكتفي بالحفظ في التدفق لاحقًا
    return redirect_to_flow(bk.id)


# ======================================================
# الصفحة الواحدة (تتغيّر واجهتها حسب الحالة والدور)
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

    # تحقق أن المستخدم طرف في العملية
    if not (is_renter(user, bk) or is_owner(user, bk)):
        raise HTTPException(status_code=403, detail="Forbidden")

    item = db.get(Item, bk.item_id)
    owner = db.get(User, bk.owner_id)
    renter = db.get(User, bk.renter_id)

    ctx = {
        "request": request,
        "title": "الحجز",
        "session_user": request.session.get("user"),
        "booking": bk,
        "item": item,
        "owner": owner,
        "renter": renter,

        # أدوار
        "i_am_owner": is_owner(user, bk),
        "i_am_renter": is_renter(user, bk),

        # حالات مختصرة للعرض الشرطي بالقالب
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
# قرار المالك: قبول/رفض + تحديد الديبو (اختياري)
# ======================================================
@router.post("/bookings/{booking_id}/owner/decision")
def owner_decision(
    booking_id: int,
    decision: Literal["accepted", "rejected"] = Form(...),
    deposit_amount: int = Form(0),
    request: Request = None,  # ← لن تُستخدم كنموذج؛ مجرد تسهيل للتوقيع
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
        bk.owner_decision = "rejected"
        bk.timeline_owner_decided_at = datetime.utcnow()
        db.commit()
        return redirect_to_flow(bk.id)

    # قبول
    bk.owner_decision = "accepted"
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
    request: Request = None,  # للتوقيع فقط
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
        # كاش: بدون ديبو (حسب طلبك)
        bk.payment_method = "cash"
        bk.payment_status = "unpaid"   # سيدفع يدويًا عند الاستلام
        bk.status = "awaiting_pickup"  # الانتظار حتى يستلم المستأجر الغرض
        bk.timeline_payment_method_chosen_at = datetime.utcnow()
        db.commit()
        return redirect_to_flow(bk.id)

    # أونلاين: سيدفع الآن (الإيجار + الديبو)، التحويل للمالك يتم عند "تم الاستلام"
    bk.payment_method = "online"
    bk.timeline_payment_method_chosen_at = datetime.utcnow()
    db.commit()
    return redirect_to_flow(bk.id)


# ======================================================
# (أونلاين) تنفيذ الدفع الآن — Placeholder لStripe
# ======================================================
@router.post("/bookings/{booking_id}/renter/pay_online")
def renter_pay_online(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    لاحقًا سننشئ PaymentIntent + Hold للديبو عبر Stripe.
    الآن: نحاكي نجاح الدفع وننتقل للحالة awaiting_pickup.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter can pay")

    if bk.payment_method != "online" or bk.status != "pending_payment":
        raise HTTPException(status_code=400, detail="Invalid state")

    # TODO (Stripe):
    # - create PaymentIntent(amount = total_amount)
    # - place a separate hold for deposit (if deposit_amount > 0)
    # - on success:
    bk.payment_status = "paid"
    if (bk.deposit_amount or 0) > 0:
        bk.deposit_status = "held"
        bk.deposit_hold_id = "HOLD_SIMULATED_ID"

    bk.status = "awaiting_pickup"  # ينتظر أن يأخذ المستأجر الغرض من المالك
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
    # - كاش: دفع للمـالك يدويًا الآن.
    # - أونلاين: نُحوِّل مبلغ الإيجار للمالك (Stripe transfer لاحقًا).
    if bk.payment_method == "online":
        # TODO: Stripe — Transfer payout for rental amount to owner
        bk.payment_status = "released"  # مبلغ الإيجار حُوِّل
        bk.timeline_rental_released_at = datetime.utcnow()

    bk.status = "in_use"  # الغرض الآن مع المستأجر
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

    # بعد تأكيد الإرجاع، ندخل مراجعة الديبو
    bk.status = "in_review"
    bk.timeline_owner_returned_at = datetime.utcnow()
    db.commit()

    return redirect_to_flow(bk.id)


# ======================================================
# قرار الديبو — المالك (إرجاعه كامل/جزئي/حجزه)
# ======================================================
@router.post("/bookings/{booking_id}/owner/deposit_action")
def owner_deposit_action(
    booking_id: int,
    action: Literal["refund_all", "withhold_partial", "withhold_all"] = Form(...),
    partial_amount: int = Form(0),
    note: str = Form(""),
    request: Request = None,  # للتوقيع فقط
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    المالك يقرر مصير الديبو بعد الإرجاع.
    - refund_all: إرجاع كامل.
    - withhold_partial: اقتطاع جزئي (partial_amount).
    - withhold_all: حجزه كله.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can decide deposit")

    if bk.status != "in_review":
        raise HTTPException(status_code=400, detail="Invalid state")

    dep = max(0, bk.deposit_amount or 0)
    if dep == 0:
        # لا يوجد ديبو — نغلق العملية فورًا
        bk.status = "completed"
        bk.timeline_closed_at = datetime.utcnow()
        db.commit()
        return redirect_to_flow(bk.id)

    # TODO (Stripe):
    # - refund to renter
    # - capture partial for owner
    # - capture all for owner
    if action == "refund_all":
        bk.deposit_status = "refunded"
        # stripe_release_deposit_all(bk.deposit_hold_id)
    elif action == "withhold_partial":
        amt = max(0, int(partial_amount or 0))
        if amt <= 0 or amt >= dep:
            raise HTTPException(status_code=400, detail="Invalid partial amount")
        bk.deposit_status = "partially_withheld"
        # stripe_capture_deposit_partial(bk.deposit_hold_id, amt)
    elif action == "withhold_all":
        bk.deposit_status = "partially_withheld"  # توحيد التسمية
        # stripe_capture_deposit_all(bk.deposit_hold_id)
    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    bk.status = "completed"
    bk.timeline_closed_at = datetime.utcnow()
    db.commit()

    return redirect_to_flow(bk.id)


# ======================================================
# وسيلة اختيارية: للمالك لو أراد وضع الحالة “بانتظار الاسترجاع”
# لمن اختار كاش وكان الغرض في الاستخدام.
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
# JSON صغير لإرجاع حالة الحجز (لو أردت polling في الواجهة)
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
        "owner_decision": bk.owner_decision,
        "payment_method": bk.payment_method,
        "payment_status": bk.payment_status,
        "deposit_amount": bk.deposit_amount,
        "deposit_status": bk.deposit_status,
    })