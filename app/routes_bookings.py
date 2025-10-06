# routes_bookings.py
from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime, date, timedelta
import os  # [جديد] لقراءة STRIPE_SECRET_KEY

from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from .database import get_db
from .models import User, Item, Booking
from .utils import category_label
from .notifications_api import push_notification, notify_admins  # تأكد من وجوده

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

# عمود ترتيب آمن بحسب أعمدة النموذج الموجودة فعليًا
def _booking_order_col():
    if hasattr(Booking, "created_at"):
        return Booking.created_at.desc()
    if hasattr(Booking, "timeline_created_at"):
        return Booking.timeline_created_at.desc()
    return Booking.id.desc()

# [جديد] دالة مساعدة: التقاط مبلغ الإيجار من Stripe إن كان مفوضًا (manual capture)
def _try_capture_stripe_rent(bk: Booking) -> bool:
    """
    يحاول التقاط (capture) مبلغ الإيجار المفوَّض على Stripe.
    يرجّع True لو نجح الالتقاط، False لو لم يُنفّذ لأي سبب (عدم وجود مفتاح/Intent/فشل).
    لا يرمي استثناءً — آمن.
    """
    try:
        import stripe  # ستعمل فقط إذا stripe مُثبت
        sk = os.getenv("STRIPE_SECRET_KEY", "")
        if not sk:
            return False
        stripe.api_key = sk
        pi_id = getattr(bk, "online_payment_intent_id", None)
        if not pi_id:
            return False
        # تنفيذ الالتقاط
        stripe.PaymentIntent.capture(pi_id)
        # تحديث الحجز محليًا
        bk.payment_status = "released"
        bk.online_status = "captured"
        bk.rent_released_at = datetime.utcnow()
        return True
    except Exception:
        return False

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

# ===== إنشاء الحجز (POST) آمن لأي نموذج =====
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

        # إشعار للمالك بوجود طلب جديد
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
    ctx = {
        "request": request,
        "title": "الحجز",
        "session_user": request.session.get("user"),
        "booking": bk,
        "item": item,
        "owner": owner,
        "renter": renter,
        "item_title": (item.title if item else f"#{bk.item_id}"),
        "category_label": category_label,
        "is_owner": is_owner(user, bk),
        "is_renter": is_renter(user, bk),
        "i_am_owner": is_owner(user, bk),
        "i_am_renter": is_renter(user, bk),
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

# ===== قرار المالك (المسار الحديث) =====
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
    bk.deposit_amount = max(0, int(deposit_amount or 0))
    bk.accepted_at = datetime.utcnow()
    bk.timeline_owner_decided_at = datetime.utcnow()
    bk.status = "accepted"
    db.commit()

    dep_txt = f" وديبو {bk.deposit_amount}$" if (bk.deposit_amount or 0) > 0 else ""
    push_notification(db, bk.renter_id, "تم قبول الحجز",
                      f"على '{item.title}'. اختر طريقة الدفع{dep_txt}.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# ===== اختيار طريقة الدفع (حديث) =====
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

# ===== دفع أونلاين (حديث) =====
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
    if bk.payment_method != "online" or bk.status not in ("accepted", "pending_payment"):
        raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)

    bk.payment_status = "paid"
    if (bk.deposit_amount or 0) > 0:
        bk.deposit_status = "held"
        bk.deposit_hold_id = "HOLD_SIMULATED_ID"

    bk.status = "paid"
    bk.timeline_paid_at = datetime.utcnow()
    db.commit()

    push_notification(db, bk.owner_id, "تم الدفع أونلاين",
                      f"حجز '{item.title}'. سلّم الغرض عند الموعد.",
                      f"/bookings/flow/{bk.id}", "booking")
    push_notification(db, bk.renter_id, "تم استلام دفعتك",
                      f"حجز '{item.title}'. توجه للاستلام حسب الموعد.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# ===== تأكيد استلام المستأجر (حديث) =====
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

    # كان سابقًا يتم الضبط مباشرة كـ captured — الآن نحاول الالتقاط الحقيقي عبر Stripe أولاً
    captured = False
    if bk.payment_method == "online":
        # محاولة التقاط المبلغ المفوض (manual capture) إن توفر Stripe + Intent
        captured = _try_capture_stripe_rent(bk)
        if not captured:
            # احتفاظ بالسلوك السابق كتراجع آمن (تجريبي/محلي)
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

# ======= Aliases للمسارات القديمة المستخدمة في القالب =======

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
                     rent_amount: int = Form(...),
                     deposit_amount: int = Form(0),
                     db: Session = Depends(get_db),
                     user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter")
    if bk.status != "accepted":
        return _redir(bk.id)

    item = db.get(Item, bk.item_id)
    bk.payment_method = "online"
    bk.rent_amount = max(0, int(rent_amount or 0))
    bk.hold_deposit_amount = max(0, int(deposit_amount or 0))
    bk.payment_status = "paid"
    bk.online_status = "paid"
    bk.deposit_status = "held" if bk.hold_deposit_amount > 0 else "none"
    bk.status = "paid"
    bk.timeline_paid_at = datetime.utcnow()
    db.commit()

    push_notification(db, bk.owner_id, "تم الدفع أونلاين",
                      f"حجز '{item.title}'. سلّم الغرض عند الموعد.",
                      f"/bookings/flow/{bk.id}", "booking")
    push_notification(db, bk.renter_id, "تم استلام دفعتك",
                      f"حجز '{item.title}'. توجه للاستلام حسب الموعد.",
                      f"/bookings/flow/{bk.id}", "booking")
    return _redir(bk.id)

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
        # [جديد] نحاول الالتقاط الحقيقي عبر Stripe، وإن لم يتوفر/فشل نرجع للسلوك المحلي السابق
        captured = _try_capture_stripe_rent(bk)
        if captured:
            # التحديثات تمت داخل الدالة
            pass
        else:
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
                      f"الغرض '{item.title}' أُرجِع. بانتظار مراجعة الإدارة للديبو.",
                      f"/bookings/flow/{bk.id}", "deposit")
    push_notification(db, bk.renter_id, "بانتظار مراجعة الديبو",
                      f"سيتم إشعارك بعد مراجعة الإدارة لحالة الديبو لحجز '{item.title}'.",
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