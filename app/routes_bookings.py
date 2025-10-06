# routes_bookings.py
from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Item, Booking
from .utils import category_label
from .notifications_api import push_notification, notify_admins  # <<< جديد

router = APIRouter(tags=["bookings"])

# ------------- Helpers -------------
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

# ------------- UI: صفحة إنشاء -------------
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
        "request": request, "title": "اختيار مدة الحجز", "session_user": request.session.get("user"),
        "item": item, "start_default": today.isoformat(),
        "end_default": (today + timedelta(days=1)).isoformat(), "days_default": 1,
    }
    return request.app.templates.TemplateResponse("booking_new.html", ctx)

# ------------- إنشاء الحجز (POST) -------------
@router.post("/bookings")
def create_booking(
    request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user),
    item_id: int = Form(...), start_date: str = Form(...), end_date: str = Form(...),
    days: Optional[int] = Form(None), pay_method: Optional[Literal["online", "cash"]] = Form(None),
):
    require_auth(user)
    item = db.get(Item, item_id)
    if not item or item.is_active != "yes":
        raise HTTPException(status_code=404, detail="Item not available")
    if item.owner_id == user.id:
        raise HTTPException(status_code=400, detail="Owner cannot book own item")

    try:
        sd, ed = _parse_date(start_date), _parse_date(end_date)
        if ed <= sd: raise ValueError
    except Exception:
        return RedirectResponse(url=f"/bookings/new?item_id={item_id}&err=dates", status_code=303)

    days = max(1, days or (ed - sd).days)
    price_per_day = item.price_per_day or 0
    total_amount = days * max(0, price_per_day)

    bk = Booking(
        item_id=item.id, renter_id=user.id, owner_id=item.owner_id,
        start_date=sd, end_date=ed, days=days,
        price_per_day_snapshot=price_per_day, total_amount=total_amount,
        status="requested",
        owner_decision=None, payment_method=None, payment_status="unpaid",
        deposit_amount=0, deposit_status=None, deposit_hold_id=None,
        timeline_created_at=datetime.utcnow(),
    )
    db.add(bk); db.commit(); db.refresh(bk)

    # إشعار للمالك: طلب حجز جديد
    push_notification(
        db, user_id=item.owner_id,
        title="طلب حجز جديد",
        body=f"على '{item.title}' من {sd} إلى {ed} ({days} يوم).",
        url=f"/bookings/flow/{bk.id}",
        kind="booking"
    )

    return redirect_to_flow(bk.id)

# ------------- صفحة التدفق -------------
@router.get("/bookings/flow/{booking_id}")
def booking_flow_page(
    booking_id: int, request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not (is_renter(user, bk) or is_owner(user, bk)):
        raise HTTPException(status_code=403, detail="Forbidden")
    item = db.get(Item, bk.item_id)
    owner, renter = db.get(User, bk.owner_id), db.get(User, bk.renter_id)
    ctx = {
        "request": request, "title": "الحجز", "session_user": request.session.get("user"),
        "booking": bk, "item": item, "owner": owner, "renter": renter,
        "item_title": (item.title if item else f"#{bk.item_id}"), "category_label": category_label,
        "is_owner": is_owner(user, bk), "is_renter": is_renter(user, bk),
        "i_am_owner": is_owner(user, bk), "i_am_renter": is_renter(user, bk),
        "is_requested": bk.status == "requested",
        "is_declined": bk.status == "declined",
        "is_pending_payment": bk.status == "pending_payment",
        "is_awaiting_pickup": bk.status == "awaiting_pickup",
        "is_in_use": bk.status == "in_use",
        "is_awaiting_return": bk.status == "awaiting_return",
        "is_in_review": bk.status == "in_review",
        "is_completed": bk.status == "completed",
    }
    return request.app.templates.TemplateResponse("booking_flow.html", ctx)

# ------------- قرار المالك -------------
@router.post("/bookings/{booking_id}/owner/decision")
def owner_decision(
    booking_id: int, decision: Literal["accepted", "rejected"] = Form(...),
    deposit_amount: int = Form(0),
    request: Request = None, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk): raise HTTPException(status_code=403, detail="Only owner can decide")
    if bk.status != "requested": raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)

    if decision == "rejected":
        bk.status = "rejected"; bk.owner_decision = "rejected"
        bk.rejected_at = datetime.utcnow(); bk.timeline_owner_decided_at = datetime.utcnow()
        db.commit()
        # إشعار للمستأجر: رفض
        push_notification(
            db, user_id=bk.renter_id,
            title="تم رفض الحجز",
            body=f"تم رفض طلبك على '{item.title}'.",
            url=f"/bookings/flow/{bk.id}", kind="booking"
        )
        return redirect_to_flow(bk.id)

    bk.owner_decision = "accepted"
    bk.deposit_amount = max(0, int(deposit_amount or 0))
    bk.accepted_at = datetime.utcnow(); bk.timeline_owner_decided_at = datetime.utcnow()
    bk.status = "accepted"
    db.commit()

    # إشعار للمستأجر: قبول
    dep_txt = f" وديبو {bk.deposit_amount}$" if (bk.deposit_amount or 0) > 0 else ""
    push_notification(
        db, user_id=bk.renter_id,
        title="تم قبول الحجز",
        body=f"على '{item.title}'. اختر طريقة الدفع{dep_txt}.",
        url=f"/bookings/flow/{bk.id}", kind="booking"
    )
    return redirect_to_flow(bk.id)

# ------------- اختيار طريقة الدفع -------------
@router.post("/bookings/{booking_id}/renter/choose_payment")
def renter_choose_payment(
    booking_id: int, method: Literal["cash", "online"] = Form(...),
    request: Request = None, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk): raise HTTPException(status_code=403, detail="Only renter can choose")
    if bk.status != "accepted": raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)

    if method == "cash":
        bk.payment_method = "cash"; bk.payment_status = "unpaid"; bk.status = "paid"
        bk.timeline_payment_method_chosen_at = datetime.utcnow()
        db.commit()
        # إشعار للمالك: المستأجر اختار كاش
        push_notification(
            db, user_id=bk.owner_id,
            title="المستأجر اختار الدفع كاش",
            body=f"حجز '{item.title}'. سيتم الدفع عند الاستلام.",
            url=f"/bookings/flow/{bk.id}", kind="booking"
        )
        return redirect_to_flow(bk.id)

    bk.payment_method = "online"
    bk.timeline_payment_method_chosen_at = datetime.utcnow()
    db.commit()

    # إشعار للمالك: اختار أونلاين (ينتظر الدفع)
    push_notification(
        db, user_id=bk.owner_id,
        title="اختير الدفع أونلاين",
        body=f"حجز '{item.title}'. بانتظار دفع المستأجر.",
        url=f"/bookings/flow/{bk.id}", kind="booking"
    )
    return redirect_to_flow(bk.id)

# ------------- دفع أونلاين (وهمي) -------------
@router.post("/bookings/{booking_id}/renter/pay_online")
def renter_pay_online(
    booking_id: int, request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk): raise HTTPException(status_code=403, detail="Only renter can pay")
    if bk.payment_method != "online" or bk.status not in ("accepted", "pending_payment"):
        raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)

    bk.payment_status = "paid"
    if (bk.deposit_amount or 0) > 0:
        bk.deposit_status = "held"; bk.deposit_hold_id = "HOLD_SIMULATED_ID"
    bk.status = "paid"; bk.timeline_paid_at = datetime.utcnow()
    db.commit()

    # إشعار للطرفين: تم الدفع
    push_notification(
        db, user_id=bk.owner_id,
        title="تم الدفع أونلاين",
        body=f"حجز '{item.title}'. سلّم الغرض عند الموعد.",
        url=f"/bookings/flow/{bk.id}", kind="booking"
    )
    push_notification(
        db, user_id=bk.renter_id,
        title="تم استلام دفعتك",
        body=f"حجز '{item.title}'. توجه للاستلام حسب الموعد.",
        url=f"/bookings/flow/{bk.id}", kind="booking"
    )
    return redirect_to_flow(bk.id)

# ------------- تأكيد استلام المستأجر -------------
@router.post("/bookings/{booking_id}/renter/confirm_received")
def renter_confirm_received(
    booking_id: int, request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk): raise HTTPException(status_code=403, detail="Only renter can confirm")
    if bk.status != "paid": raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)

    if bk.payment_method == "online":
        bk.payment_status = "released"
        bk.owner_payout_amount = bk.rent_amount or bk.total_amount or 0
        bk.rent_released_at = datetime.utcnow(); bk.online_status = "captured"

    bk.status = "picked_up"; bk.picked_up_at = datetime.utcnow(); bk.timeline_renter_received_at = datetime.utcnow()
    db.commit()

    # إشعار للمالك: تم الاستلام
    push_notification(
        db, user_id=bk.owner_id,
        title="المستأجر استلم الغرض",
        body=f"'{item.title}'. تذكير بموعد الإرجاع.",
        url=f"/bookings/flow/{bk.id}", kind="booking"
    )
    # إشعار للمستأجر: تذكير بالإرجاع
    push_notification(
        db, user_id=bk.renter_id,
        title="تم الاستلام بنجاح",
        body=f"لا تنسَ إرجاع '{item.title}' في الموعد.",
        url=f"/bookings/flow/{bk.id}", kind="booking"
    )

    return redirect_to_flow(bk.id)

# ------------- (نسخة إدمن) إقفال الديبو القديم -------------
@router.post("/bookings/{booking_id}/owner-confirm-return-admin")
def _legacy_owner_confirm_return_admin(
    booking_id: int, action: Literal["ok", "charge"] = Form(...),
    charge_amount: int = Form(0), owner_note: str = Form(""),
    db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user),
    request: Request = None,
):
    require_auth(user)
    if getattr(user, "role", "") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can decide deposit")

    bk = require_booking(db, booking_id)
    if bk.status not in ("returned", "in_review", "picked_up"):
        return redirect_to_flow(bk.id)

    item = db.get(Item, bk.item_id)

    if bk.status != "in_review":
        bk.status = "in_review"

    dep = max(0, bk.hold_deposit_amount or bk.deposit_amount or 0)
    now = datetime.utcnow()

    if dep == 0:
        bk.deposit_status = "none"; bk.deposit_charged_amount = 0
    else:
        if action == "ok":
            bk.deposit_status = "refunded"; bk.deposit_charged_amount = 0
        else:
            amt = max(0, int(charge_amount or 0))
            if amt >= dep:
                bk.deposit_status = "claimed"; bk.deposit_charged_amount = dep
            else:
                bk.deposit_status = "partially_withheld"; bk.deposit_charged_amount = amt

    bk.owner_return_note = (owner_note or "").strip()
    bk.status = "closed"; bk.return_confirmed_by_owner_at = now; bk.timeline_closed_at = now
    db.commit()

    # إشعارات الديبو
    if bk.deposit_status in ("refunded", "none"):
        push_notification(
            db, user_id=bk.renter_id,
            title="ديبوك سيُعاد",
            body=f"تمت الموافقة على إعادة الديبو لحجز '{item.title}'.",
            url=f"/bookings/flow/{bk.id}", kind="deposit"
        )
        push_notification(
            db, user_id=bk.owner_id,
            title="تمت إعادة الديبو",
            body=f"لا توجد مشاكل على '{item.title}'.",
            url=f"/bookings/flow/{bk.id}", kind="deposit"
        )
    else:
        msg = "تم خصم كامل الديبو" if bk.deposit_status == "claimed" else f"تم خصم جزئي ({bk.deposit_charged_amount}$)"
        push_notification(
            db, user_id=bk.renter_id,
            title="قرار الديبو",
            body=f"{msg} لحجز '{item.title}'.",
            url=f"/bookings/flow/{bk.id}", kind="deposit"
        )
        push_notification(
            db, user_id=bk.owner_id,
            title="تم تطبيق قرار الديبو",
            body=msg + f" على '{item.title}'.",
            url=f"/bookings/flow/{bk.id}", kind="deposit"
        )

    return redirect_to_flow(bk.id)

# ------------- (إدمن) القرار النهائي للديبو -------------
@router.post("/bookings/{booking_id}/owner/deposit_action")
def owner_deposit_action(
    booking_id: int,
    action: Literal["refund_all", "withhold_partial", "withhold_all"] = Form(...),
    partial_amount: int = Form(0), note: str = Form(""),
    request: Request = None, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    if getattr(user, "role", "") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can decide deposit")

    bk = require_booking(db, booking_id)
    if bk.status != "in_review": raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)
    dep = max(0, bk.deposit_amount or 0)

    if dep == 0:
        bk.deposit_status = "none"; bk.status = "completed"; bk.timeline_closed_at = datetime.utcnow()
        db.commit()
        push_notification(db, bk.renter_id, "لا يوجد ديبو", f"حجز '{item.title}' أغلق بدون ديبو.", f"/bookings/flow/{bk.id}", "deposit")
        push_notification(db, bk.owner_id, "أُغلق الحجز", "لم يكن هناك ديبو.", f"/bookings/flow/{bk.id}", "deposit")
        return redirect_to_flow(bk.id)

    if action == "refund_all":
        bk.deposit_status = "refunded"; bk.deposit_charged_amount = 0
        renter_msg = "تمت إعادة كامل الديبو."
    elif action == "withhold_partial":
        amt = max(0, int(partial_amount or 0))
        if amt <= 0 or amt >= dep: raise HTTPException(status_code=400, detail="Invalid partial amount")
        bk.deposit_status = "partially_withheld"; bk.deposit_charged_amount = amt
        renter_msg = f"تم خصم {amt}$ من الديبو وإعادة الباقي."
    elif action == "withhold_all":
        bk.deposit_status = "claimed"; bk.deposit_charged_amount = dep
        renter_msg = "تم خصم كامل الديبو."
    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    bk.owner_return_note = (note or "").strip()
    bk.status = "completed"; bk.timeline_closed_at = datetime.utcnow()
    db.commit()

    # إشعار نهائي للديبو
    push_notification(db, bk.renter_id, "قرار الديبو", f"{renter_msg} لحجز '{item.title}'.", f"/bookings/flow/{bk.id}", "deposit")
    push_notification(db, bk.owner_id, "تطبيق قرار الديبو", renter_msg, f"/bookings/flow/{bk.id}", "deposit")
    return redirect_to_flow(bk.id)

# ------------- مسارات القالب القديم (أبقيناها) -------------
@router.post("/bookings/{booking_id}/accept")
def _legacy_accept(booking_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user), request: Request = None):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk): raise HTTPException(status_code=403, detail="Only owner can accept")
    if bk.status != "requested": return redirect_to_flow(bk.id)
    bk.status = "accepted"; bk.owner_decision = "accepted"
    bk.accepted_at = datetime.utcnow(); bk.timeline_owner_decided_at = datetime.utcnow()
    db.commit()
    item = db.get(Item, bk.item_id)
    push_notification(db, bk.renter_id, "تم قبول الحجز", f"على '{item.title}'. اختر طريقة الدفع.", f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

@router.post("/bookings/{booking_id}/reject")
def _legacy_reject(booking_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user), request: Request = None):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk): raise HTTPException(status_code=403, detail="Only owner can reject")
    if bk.status != "requested": return redirect_to_flow(bk.id)
    bk.status = "rejected"; bk.owner_decision = "rejected"
    bk.rejected_at = datetime.utcnow(); bk.timeline_owner_decided_at = datetime.utcnow()
    db.commit()
    item = db.get(Item, bk.item_id)
    push_notification(db, bk.renter_id, "تم رفض الحجز", f"على '{item.title}'.", f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

@router.post("/bookings/{booking_id}/pay-cash")
def _legacy_pay_cash(booking_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user), request: Request = None):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk): raise HTTPException(status_code=403, detail="Only renter")
    if bk.status != "accepted": return redirect_to_flow(bk.id)
    bk.payment_method = "cash"; bk.online_status = None
    bk.hold_deposit_amount = 0; bk.deposit_status = "none"; bk.payment_status = "unpaid"
    bk.status = "paid"; bk.timeline_payment_method_chosen_at = datetime.utcnow()
    db.commit()
    item = db.get(Item, bk.item_id)
    push_notification(db, bk.owner_id, "اختيار الدفع كاش", f"حجز '{item.title}'. سيتم الدفع عند الاستلام.", f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

@router.post("/bookings/{booking_id}/pay-online")
def _legacy_pay_online(booking_id: int, rent_amount: int = Form(...), deposit_amount: int = Form(0),
                       db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user), request: Request = None):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk): raise HTTPException(status_code=403, detail="Only renter")
    if bk.status != "accepted": return redirect_to_flow(bk.id)
    bk.payment_method = "online"
    bk.rent_amount = max(0, int(rent_amount or 0))
    bk.hold_deposit_amount = max(0, int(deposit_amount or 0))
    bk.payment_status = "paid"; bk.online_status = "paid"
    bk.deposit_status = "held" if bk.hold_deposit_amount > 0 else "none"
    bk.status = "paid"; bk.timeline_paid_at = datetime.utcnow()
    db.commit()
    item = db.get(Item, bk.item_id)
    push_notification(db, bk.owner_id, "تم الدفع أونلاين", f"حجز '{item.title}'. سلّم الغرض.", f"/bookings/flow/{bk.id}", "booking")
    push_notification(db, bk.renter_id, "تم استلام دفعتك", f"حجز '{item.title}'. توجه للاستلام.", f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

@router.post("/bookings/{booking_id}/picked-up")
def _legacy_picked_up(booking_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user), request: Request = None):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk): raise HTTPException(status_code=403, detail="Only renter")
    if bk.status != "paid": return redirect_to_flow(bk.id)
    bk.status = "picked_up"; bk.picked_up_at = datetime.utcnow()
    if bk.payment_method == "online":
        bk.owner_payout_amount = bk.rent_amount or bk.total_amount or 0
        bk.rent_released_at = datetime.utcnow(); bk.online_status = "captured"; bk.payment_status = "released"
    db.commit()
    item = db.get(Item, bk.item_id)
    push_notification(db, bk.owner_id, "المستأجر استلم الغرض", f"'{item.title}'.", f"/bookings/flow/{bk.id}", "booking")
    push_notification(db, bk.renter_id, "تم الاستلام", f"تذكير بالإرجاع في الموعد.", f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

@router.post("/bookings/{booking_id}/mark-returned")
def _legacy_mark_returned(booking_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user), request: Request = None):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk): raise HTTPException(status_code=403, detail="Only renter")
    if bk.status != "picked_up": return redirect_to_flow(bk.id)
    bk.status = "returned"; bk.returned_at = datetime.utcnow()
    db.commit()
    item = db.get(Item, bk.item_id)
    # إشعار للطرفين بمرحلة المراجعة/الديبو
    push_notification(db, bk.owner_id, "تم تعليم الإرجاع", f"تفقد '{item.title}' وراجع الديبو.", f"/bookings/flow/{bk.id}", "deposit")
    push_notification(db, bk.renter_id, "بانتظار مراجعة الديبو", f"إن لم توجد مشكلة سيُعاد ديبوك.", f"/bookings/flow/{bk.id}", "deposit")
    # إشعار إدمن: هناك إرجاع بانتظار قرار
    notify_admins(db, "إرجاع بانتظار قرار الديبو", f"Booking #{bk.id} على '{item.title}'", f"/bookings/flow/{bk.id}")
    return redirect_to_flow(bk.id)

# ------------- JSON حالة الحجز -------------
@router.get("/api/bookings/{booking_id}/state")
def booking_state(booking_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not (is_renter(user, bk) or is_owner(user, bk)): raise HTTPException(status_code=403, detail="Forbidden")
    return _json({
        "id": bk.id, "status": bk.status, "owner_decision": bk.owner_decision,
        "payment_method": bk.payment_method, "payment_status": bk.payment_status,
        "deposit_amount": bk.deposit_amount, "deposit_status": bk.deposit_status,
    })

# ------------- صفحة قائمة الحجوزات -------------
@router.get("/bookings")
def bookings_index(request: Request, view: Literal["renter", "owner"] = "renter",
                   db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    q = db.query(Booking)
    if view == "owner":
        q = q.filter(Booking.owner_id == user.id); title = "حجوزات على ممتلكاتي"
    else:
        q = q.filter(Booking.renter_id == user.id); title = "حجوزاتي"
    bookings = q.order_by(Booking.created_at.desc()).all()
    return request.app.templates.TemplateResponse("bookings_index.html", {
        "request": request, "title": title, "session_user": request.session.get("user"),
        "bookings": bookings, "view": view,
    })

# ------------- إشعارات الجرس (عداد + قائمة) -------------
@router.get("/api/bookings/pending-count")
def api_bookings_pending_count(db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    count = db.query(Booking).filter(Booking.owner_id == user.id, Booking.status == "requested").count()
    return _json({"count": int(count)})

@router.get("/api/bookings/pending-list")
def api_bookings_pending_list(limit: int = 10, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    require_auth(user)
    q = (db.query(Booking)
         .filter(Booking.owner_id == user.id, Booking.status == "requested")
         .order_by(Booking.created_at.desc())
         .limit(max(1, min(50, int(limit or 10)))))
    rows = q.all()

    def _title(it: Item | None) -> str:
        try: return (it.title or f"#{it.id}") if it else "عنصر محذوف"
        except Exception: return "عنصر"

    data = []
    for b in rows:
        item = db.get(Item, b.item_id)
        data.append({
            "id": b.id, "item_id": b.item_id, "item_title": _title(item),
            "start_date": str(b.start_date), "end_date": str(b.end_date),
            "days": int(b.days or 1), "url": f"/bookings/flow/{b.id}",
        })
    return _json({"items": data})