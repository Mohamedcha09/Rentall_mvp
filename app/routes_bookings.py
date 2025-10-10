# app/routes_bookings.py
# NOTE:
# قرارات الوديعة (refund/withhold) تُدار في app/pay_api.py عبر صلاحية can_manage_deposits
# هذا الملف مسؤول عن تدفّق الحجز من الإنشاء حتى الإرجاع.

from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime, date, timedelta
import os

from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from .database import get_db
from .models import User, Item, Booking
from .utils import category_label
from .notifications_api import push_notification, notify_admins

router = APIRouter(tags=["bookings"])

# ===== Helpers =====
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
    return bool(user) and user.id == bk.renter_id

def is_owner(user: User, bk: Booking) -> bool:
    return bool(user) and user.id == bk.owner_id

def redirect_to_flow(booking_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"/bookings/flow/{booking_id}", status_code=303)

def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def _json(data: dict) -> JSONResponse:
    return JSONResponse(data, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

def _booking_order_col():
    if hasattr(Booking, "created_at"):
        return Booking.created_at.desc()
    if hasattr(Booking, "timeline_created_at"):
        return Booking.timeline_created_at.desc()
    return Booking.id.desc()

# التقاط Stripe (يُستدعى عند "تم الاستلام")
def _try_capture_stripe_rent(bk: Booking) -> bool:
    try:
        import stripe
        sk = os.getenv("STRIPE_SECRET_KEY", "")
        if not sk:
            return False
        stripe.api_key = sk
        pi_id = getattr(bk, "online_payment_intent_id", None)
        if not pi_id:
            return False
        stripe.PaymentIntent.capture(pi_id)
        bk.payment_status = "released"
        bk.online_status = "captured"
        bk.rent_released_at = datetime.utcnow()
        return True
    except Exception:
        return False

# [ADDED helpers] مهلات وسياسة الوقت
DISPUTE_WINDOW_HOURS = 48  # مهلة البلاغ بعد الإرجاع
RENTER_REPLY_WINDOW_HOURS = 48  # مهلة رد المستأجر (للعرض فقط)

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None

# ===== UI: صفحة إنشاء =====
@router.get("/bookings/new")
def booking_new_page(
    request: Request,
    item_id: int = Query(..., description="معرّف العنصر المراد حجزه"),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    item = db.get(Item, item_id)
    if not item or item.is_active != "yes":
        raise HTTPException(status_code=404, detail="Item not available")
    today = date.today()
    ctx = {
        "request": request,
        "title": "اختيار مدة الحجز",
        "session_user": request.session.get("user"),
        "item": item,
        "start_default": today.isoformat(),
        "end_default": (today + timedelta(days=1)).isoformat(),
        "days_default": 1,
    }
    return request.app.templates.TemplateResponse("booking_new.html", ctx)

# ===== إنشاء الحجز =====
@router.post("/bookings")
async def create_booking(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    form = await request.form()
    q = request.query_params

    def pick(*names, default=None):
        for n in names:
            v = form.get(n)
            if v is None:
                v = q.get(n)
            if v not in (None, ""):
                return v
        return default

    try:
        item_id_raw = pick("item_id", "item", "itemId")
        if not item_id_raw:
            raise ValueError("missing item_id")
        item_id = int(item_id_raw)

        item = db.get(Item, item_id)
        if not item or item.is_active != "yes":
            raise HTTPException(status_code=404, detail="Item not available")
        if item.owner_id == user.id:
            raise HTTPException(status_code=400, detail="Owner cannot book own item")

        sd_str = pick("start_date", "date_from", "from")
        ed_str = pick("end_date", "date_to", "to")
        if not sd_str or not ed_str:
            raise ValueError("missing dates")

        sd = _parse_date(sd_str)
        ed = _parse_date(ed_str)
        if ed <= sd:
            sd, ed = ed, sd

        try:
            days = int(pick("days", default="0") or "0")
        except Exception:
            days = 0
        if days < 1:
            days = max(1, (ed - sd).days)

        price_per_day = item.price_per_day or 0
        total_amount = days * max(0, price_per_day)

        candidate = {
            "item_id": item.id,
            "renter_id": user.id,
            "owner_id": item.owner_id,
            "start_date": sd,
            "end_date": ed,
            "days": days,
            "price_per_day_snapshot": price_per_day,
            "total_amount": total_amount,
            "status": "requested",
            "owner_decision": None,
            "payment_method": None,
            "payment_status": "unpaid",
            "deposit_amount": 0,
            "deposit_status": None,
            "deposit_hold_id": None,
            "timeline_created_at": datetime.utcnow(),
        }

        booking_cols = {c.key for c in inspect(Booking).mapper.column_attrs}
        safe_data = {k: v for k, v in candidate.items() if k in booking_cols}

        bk = Booking(**safe_data)
        db.add(bk)
        db.commit()
        db.refresh(bk)

        push_notification(
            db, bk.owner_id, "طلب حجز جديد",
            f"على '{item.title}'. اضغط لعرض التفاصيل.",
            f"/bookings/flow/{bk.id}", "booking"
        )
        return redirect_to_flow(bk.id)

    except HTTPException:
        raise
    except Exception:
        item_id_for_redirect = pick("item_id", "item", "itemId", default="")
        return RedirectResponse(
            url=f"/bookings/new?item_id={item_id_for_redirect}&err=invalid",
            status_code=303
        )

# ===== صفحة التدفق =====
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

    # حالة تفعيل مدفوعات المالك لتمكين الدفع أونلاين
    owner_pe = bool(getattr(owner, "payouts_enabled", False)) if owner else False

    # [ADDED] تمرير مهلة البلاغ بعد الإرجاع لعرض عدّاد (48 ساعة)
    dispute_deadline = None
    if getattr(bk, "returned_at", None):
        try:
            dispute_deadline = bk.returned_at + timedelta(hours=DISPUTE_WINDOW_HOURS)
        except Exception:
            dispute_deadline = None

    ctx = {
        "request": request,
        "title": "الحجز",
        "session_user": request.session.get("user"),
        "booking": bk,
        "item": item,
        "owner": owner,
        "renter": renter,
        "owner_pe": owner_pe,
        "item_title": (item.title if item else f"#{bk.item_id}"),
        "category_label": category_label,
        "is_owner": is_owner(user, bk),
        "is_renter": is_renter(user, bk),
        "i_am_owner": is_owner(user, bk),
        "i_am_renter": is_renter(user, bk),
        "is_requested": (bk.status == "requested"),
        "is_declined": (bk.status == "rejected"),
        "is_pending_payment": (bk.status == "pending_payment"),
        "is_awaiting_pickup": (bk.status == "awaiting_pickup"),
        "is_in_use": (bk.status == "in_use"),
        "is_awaiting_return": (bk.status == "awaiting_return"),
        "is_in_review": (bk.status == "in_review"),
        "is_completed": (bk.status == "completed"),
        # [ADDED]
        "dispute_deadline_iso": _iso(dispute_deadline),
        "renter_reply_hours": RENTER_REPLY_WINDOW_HOURS,
    }
    return request.app.templates.TemplateResponse("booking_flow.html", ctx)

# ===== قرار المالك =====
@router.post("/bookings/{booking_id}/owner/decision")
def owner_decision(
    booking_id: int,
    decision: Literal["accepted", "rejected"] = Form(...),
    deposit_amount: int = Form(0),
    request: Request = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can decide")
    if bk.status != "requested":
        raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)

    if decision == "rejected":
        bk.status = "rejected"
        bk.owner_decision = "rejected"
        bk.rejected_at = datetime.utcnow()
        bk.timeline_owner_decided_at = datetime.utcnow()
        db.commit()
        push_notification(db, bk.renter_id, "تم رفض الحجز",
                          f"تم رفض طلبك على '{item.title}'.",
                          f"/bookings/flow/{bk.id}", "booking")
        return redirect_to_flow(bk.id)

    bk.owner_decision = "accepted"

    # افتراضي الديبو = 5 × السعر اليومي إذا لم يُدخل المالك رقمًا
    default_deposit = (item.price_per_day or 0) * 5
    amount = int(deposit_amount or 0)
    if amount <= 0:
        amount = default_deposit

    bk.deposit_amount = max(0, amount)
    bk.accepted_at = datetime.utcnow()
    bk.timeline_owner_decided_at = datetime.utcnow()
    bk.status = "accepted"
    db.commit()

    dep_txt = f" وديبو {bk.deposit_amount}$" if (bk.deposit_amount or 0) > 0 else ""
    push_notification(db, bk.renter_id, "تم قبول الحجز",
                      f"على '{item.title}'. اختر طريقة الدفع{dep_txt}.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# ===== اختيار طريقة الدفع =====
@router.post("/bookings/{booking_id}/renter/choose_payment")
def renter_choose_payment(
    booking_id: int,
    method: Literal["cash", "online"] = Form(...),
    request: Request = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter can choose")
    if bk.status != "accepted":
        raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)

    if method == "cash":
        bk.payment_method = "cash"
        bk.payment_status = "unpaid"
        bk.status = "paid"
        bk.timeline_payment_method_chosen_at = datetime.utcnow()
        db.commit()
        push_notification(db, bk.owner_id, "المستأجر اختار الدفع كاش",
                          f"حجز '{item.title}'. سيتم الدفع عند الاستلام.",
                          f"/bookings/flow/{bk.id}", "booking")
        return redirect_to_flow(bk.id)

    bk.payment_method = "online"
    bk.timeline_payment_method_chosen_at = datetime.utcnow()
    db.commit()
    push_notification(db, bk.owner_id, "اختير الدفع أونلاين",
                      f"حجز '{item.title}'. بانتظار دفع المستأجر.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# ===== دفع أونلاين — منع إن لم يُفعّل المالك الاستلام =====
@router.post("/bookings/{booking_id}/renter/pay_online")
def renter_pay_online(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter can pay")
    if bk.status != "accepted":
        return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

    owner = db.get(User, bk.owner_id)
    owner_pe = bool(getattr(owner, "payouts_enabled", False)) if owner else False
    if not owner_pe:
        raise HTTPException(status_code=409, detail="Owner payouts not enabled")

    return RedirectResponse(url=f"/api/stripe/checkout/rent/{booking_id}", status_code=303)

# ===== تأكيد استلام المستأجر =====
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
    if bk.status != "paid":
        raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)

    captured = False
    if bk.payment_method == "online":
        captured = _try_capture_stripe_rent(bk)
        if not captured:
            bk.payment_status = "released"
            bk.owner_payout_amount = bk.rent_amount or bk.total_amount or 0
            bk.rent_released_at = datetime.utcnow()
            bk.online_status = "captured"

    bk.status = "picked_up"
    bk.picked_up_at = datetime.utcnow()
    bk.timeline_renter_received_at = datetime.utcnow()
    db.commit()

    push_notification(db, bk.owner_id, "المستأجر استلم الغرض",
                      f"'{item.title}'. تذكير بموعد الإرجاع.",
                      f"/bookings/flow/{bk.id}", "booking")
    push_notification(db, bk.renter_id, "تم الاستلام بنجاح",
                      f"لا تنسَ إرجاع '{item.title}' في الموعد.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# [ADDED] تأكيد المالك للتسليم (زر "تمّ التسليم" عند المالك)
@router.post("/bookings/{booking_id}/owner/confirm_delivered")
def owner_confirm_delivered(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يسمح للمالك بتعليم أن الغرض تمّ تسليمه للمستأجر.
    - يلتقط دفعة الإيجار إذا كانت أونلاين (manual capture).
    - يغيّر الحالة إلى picked_up.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can confirm delivery")
    if bk.status not in ("paid",):  # تم دفعها (كاش/أونلاين مؤهَّلة للتسليم)
        return redirect_to_flow(bk.id)

    item = db.get(Item, bk.item_id)

    if bk.payment_method == "online":
        captured = _try_capture_stripe_rent(bk)
        if not captured:
            bk.payment_status = "released"
            bk.owner_payout_amount = bk.rent_amount or bk.total_amount or 0
            bk.rent_released_at = datetime.utcnow()
            bk.online_status = "captured"

    bk.status = "picked_up"
    bk.picked_up_at = datetime.utcnow()
    db.commit()

    push_notification(db, bk.renter_id, "تمّ تسليم الغرض",
                      f"قام المالك بتسليم '{item.title}'. نتمنى لك تجربة موفقة.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# [ADDED] اختصار لفتح بلاغ وديعة من صفحة التدفق (ينقل لمسار البلاغ)
@router.post("/bookings/{booking_id}/owner/open_deposit_issue")
def owner_open_deposit_issue(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    اختصار ينقل إلى فورم البلاغ الموجود في routes_deposits.py
    POST الحقيقي يكون على: /deposits/{booking_id}/report
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner")
    return RedirectResponse(url=f"/deposits/{bk.id}/report", status_code=303)

# [ADDED] API يُرجع مهلة البلاغ وردّ المستأجر بصيغة ISO لعرض عدّادات
@router.get("/api/bookings/{booking_id}/deadlines")
def booking_deadlines(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not (is_renter(user, bk) or is_owner(user, bk)):
        raise HTTPException(status_code=403, detail="Forbidden")

    dispute_deadline = None
    renter_reply_deadline = None

    if getattr(bk, "returned_at", None):
        try:
            dispute_deadline = bk.returned_at + timedelta(hours=DISPUTE_WINDOW_HOURS)
        except Exception:
            dispute_deadline = None

    # مبدئيًا لا نملك طابعًا زمنيًا لبداية النزاع لاحتساب رد المستأجر بدقة.
    # يمكن لاحقًا الاعتماد على updated_at عند دخول in_dispute، هنا نعرض قيمة إرشادية بالساعات.
    return _json({
        "dispute_deadline_iso": _iso(dispute_deadline),
        "renter_reply_window_hours": RENTER_REPLY_WINDOW_HOURS,
    })

# ======= Aliases القديمة (متروكة للتوافق) =======

def _redir(flow_id: int):
    return RedirectResponse(url=f"/bookings/flow/{flow_id}", status_code=status.HTTP_303_SEE_OTHER)

@router.api_route("/bookings/{booking_id}/accept", methods=["POST", "GET"])
def alias_accept(booking_id: int,
                 db: Session = Depends(get_db),
                 user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can accept")
    if bk.status != "requested":
        return _redir(bk.id)
    item = db.get(Item, bk.item_id)

    # قبول سريع بدون إدخال يدوي: نملأ الديبو الافتراضي
    default_deposit = (item.price_per_day or 0) * 5
    if (bk.deposit_amount or 0) <= 0:
        bk.deposit_amount = default_deposit

    bk.status = "accepted"
    bk.owner_decision = "accepted"
    bk.accepted_at = datetime.utcnow()
    bk.timeline_owner_decided_at = datetime.utcnow()
    db.commit()
    push_notification(db, bk.renter_id, "تم قبول الحجز",
                      f"على '{item.title}'. اختر طريقة الدفع.",
                      f"/bookings/flow/{bk.id}", "booking")
    return _redir(bk.id)

@router.api_route("/bookings/{booking_id}/reject", methods=["POST", "GET"])
def alias_reject(booking_id: int,
                 db: Session = Depends(get_db),
                 user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can reject")
    if bk.status != "requested":
        return _redir(bk.id)
    item = db.get(Item, bk.item_id)
    bk.status = "rejected"
    bk.owner_decision = "rejected"
    bk.rejected_at = datetime.utcnow()
    bk.timeline_owner_decided_at = datetime.utcnow()
    db.commit()
    push_notification(db, bk.renter_id, "تم رفض الحجز",
                      f"تم رفض طلبك على '{item.title}'.",
                      f"/bookings/flow/{bk.id}", "booking")
    return _redir(bk.id)

@router.post("/bookings/{booking_id}/pay-cash")
def alias_pay_cash(booking_id: int,
                   db: Session = Depends(get_db),
                   user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter")
    if bk.status != "accepted":
        return _redir(bk.id)
    item = db.get(Item, bk.item_id)
    bk.payment_method = "cash"
    bk.online_status = None
    bk.deposit_status = "none"
    bk.payment_status = "unpaid"
    bk.status = "paid"
    bk.timeline_payment_method_chosen_at = datetime.utcnow()
    db.commit()
    push_notification(db, bk.owner_id, "المستأجر اختار الدفع كاش",
                      f"حجز '{item.title}'. سيتم الدفع عند الاستلام.",
                      f"/bookings/flow/{bk.id}", "booking")
    return _redir(bk.id)

@router.post("/bookings/{booking_id}/pay-online")
def alias_pay_online(booking_id: int,
                     rent_amount: int = Form(0),
                     deposit_amount: int = Form(0),
                     db: Session = Depends(get_db),
                     user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter")
    if bk.status != "accepted":
        return _redir(bk.id)

    owner = db.get(User, bk.owner_id)
    owner_pe = bool(getattr(owner, "payouts_enabled", False)) if owner else False
    if not owner_pe:
        raise HTTPException(status_code=409, detail="Owner payouts not enabled")

    bk.payment_method = "online"
    if rent_amount:
        bk.rent_amount = max(0, int(rent_amount or 0))
    if deposit_amount:
        bk.hold_deposit_amount = max(0, int(deposit_amount or 0))
    db.commit()

    return RedirectResponse(url=f"/api/stripe/checkout/rent/{booking_id}", status_code=303)

@router.post("/bookings/{booking_id}/picked-up")
def alias_picked_up(booking_id: int,
                    db: Session = Depends(get_db),
                    user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter")
    if bk.status != "paid":
        return _redir(bk.id)

    item = db.get(Item, bk.item_id)
    bk.status = "picked_up"
    bk.picked_up_at = datetime.utcnow()

    if bk.payment_method == "online":
        captured = _try_capture_stripe_rent(bk)
        if not captured:
            bk.owner_payout_amount = bk.rent_amount or bk.total_amount or 0
            bk.rent_released_at = datetime.utcnow()
            bk.online_status = "captured"
            bk.payment_status = "released"

    db.commit()
    push_notification(db, bk.owner_id, "المستأجر استلم الغرض",
                      f"'{item.title}'. تذكير بموعد الإرجاع.",
                      f"/bookings/flow/{bk.id}", "booking")
    return _redir(bk.id)

@router.post("/bookings/{booking_id}/mark-returned")
def alias_mark_returned(booking_id: int,
                        db: Session = Depends(get_db),
                        user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter")
    if bk.status != "picked_up":
        return _redir(bk.id)

    item = db.get(Item, bk.item_id)
    bk.status = "returned"
    bk.returned_at = datetime.utcnow()
    db.commit()

    push_notification(db, bk.owner_id, "تم تعليم الإرجاع",
                      f"الغرض '{item.title}' أُرجِع. بانتظار مراجعة الإدارة للوديعة.",
                      f"/bookings/flow/{bk.id}", "deposit")
    push_notification(db, bk.renter_id, "بانتظار مراجعة الوديعة",
                      f"سيتم إشعارك بعد مراجعة الإدارة لحالة الوديعة لحجز '{item.title}'.",
                      f"/bookings/flow/{bk.id}", "deposit")
    notify_admins(db, "مراجعة ديبو مطلوبة",
                  f"حجز #{bk.id} يحتاج قرار ديبو.", f"/bookings/flow/{bk.id}")
    return _redir(bk.id)

# ===== JSON حالة الحجز =====
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

    return _json({
        "id": bk.id,
        "status": bk.status,
        "owner_decision": bk.owner_decision,
        "payment_method": bk.payment_method,
        "payment_status": bk.payment_status,
        "deposit_amount": bk.deposit_amount,
        "deposit_status": bk.deposit_status,
    })

# ===== صفحة قائمة الحجوزات =====
@router.get("/bookings")
def bookings_index(
    request: Request,
    view: Literal["renter", "owner"] = "renter",
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)

    q = db.query(Booking)
    if view == "owner":
        q = q.filter(Booking.owner_id == user.id)
        title = "حجوزات على ممتلكاتي"
    else:
        q = q.filter(Booking.renter_id == user.id)
        title = "حجوزاتي"

    q = q.order_by(_booking_order_col())
    bookings = q.all()

    return request.app.templates.TemplateResponse(
        "bookings_index.html",
        {
            "request": request,
            "title": title,
            "session_user": request.session.get("user"),
            "bookings": bookings,
            "view": view,
        },
    )