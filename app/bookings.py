# app/bookings.py
from datetime import datetime, date
from fastapi import HTTPException , APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from .database import get_db
from .models import Booking, Item, User

router = APIRouter()

import os, stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
FEE_BPS = int(os.environ.get("PLATFORM_FEE_BPS","800"))  # 8% افتراضي

def require_login(request: Request):
    return request.session.get("user")

def require_approved(request: Request):
    u = request.session.get("user")
    return u and u.get("status") == "approved"

# ---------- إنشاء حجز ----------
@router.get("/bookings/new")
def booking_new(request: Request, db: Session = Depends(get_db), item_id: int = 0):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    if not require_approved(request):
        return RedirectResponse(url="/profile", status_code=303)

    item = db.query(Item).get(item_id)
    if not item or item.is_active != "yes":
        return RedirectResponse(url="/items", status_code=303)
    if item.owner_id == u["id"]:
        # لا تحجز عنصر تملكه
        return RedirectResponse(url=f"/items/{item.id}", status_code=303)

    return request.app.templates.TemplateResponse(
        "bookings_new.html",
        {
            "request": request,
            "title": "حجز جديد",
            "item": item,
            "session_user": u
        }
    )

@router.post("/bookings/new")
def booking_create(
    request: Request,
    db: Session = Depends(get_db),
    item_id: int = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...)
):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    item = db.query(Item).get(item_id)
    if not item:
        return RedirectResponse(url="/", status_code=303)

    days = (end_date - start_date).days or 1
    total_amount = days * (item.price_per_day or 0)

    b = Booking(
        item_id=item.id,
        renter_id=u["id"],
        owner_id=item.owner_id,
        start_date=start_date,
        end_date=end_date,
        days=days,
        total_amount=total_amount,
        status="pending"
        # لا نمرر note هنا
    )
    db.add(b)
    db.commit()
    db.refresh(b)

    return RedirectResponse(url=f"/bookings/{b.id}", status_code=303)

# ---------- قائمتي ----------
@router.get("/bookings")
def my_bookings(request: Request, db: Session = Depends(get_db), view: str = "all"):   # >>> ADDED (view)
    """
    يعرض القائمتين معًا، أو واحدة حسب ?view=renter / ?view=owner
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    # حجوزاتي كمستأجر
    as_renter = (
        db.query(Booking)
        .filter(Booking.renter_id == u["id"])
        .order_by(Booking.created_at.desc())
        .all()
    )
    # طلبات على أشيائي (أنا المالك)
    as_owner = (
        db.query(Booking)
        .filter(Booking.owner_id == u["id"])
        .order_by(Booking.created_at.desc())
        .all()
    )

    def view_row(b: Booking):
        item = db.query(Item).get(b.item_id)
        return {
            "id": b.id,
            "status": b.status,
            "start_date": b.start_date,
            "end_date": b.end_date,
            "note": getattr(b, "note", "") or "",
            "item": item,
            "renter": db.query(User).get(b.renter_id),
            "owner": db.query(User).get(b.owner_id),
        }

    # >>> ADDED (تصفية حسب view)
    filtered_renter = [view_row(x) for x in as_renter] if view in ("all", "renter") else []
    filtered_owner  = [view_row(x) for x in as_owner]  if view in ("all", "owner")  else []

    return request.app.templates.TemplateResponse(
        "bookings_list.html",
        {
            "request": request,
            "title": "الحجوزات",
            "session_user": u,
            "as_renter": filtered_renter,
            "as_owner": filtered_owner,
            "current_view": view,                         # >>> ADDED
            "today": date.today(),
        }
    )

# ---------- مسارات متوافقة لتجنب 404 (اختصارات) ----------
@router.get("/my_rentals")              # >>> ADDED
def alias_my_rentals():
    # مستأجر: عرض حجوزاتي
    return RedirectResponse(url="/bookings?view=renter", status_code=303)

@router.get("/owner/bookings")          # >>> ADDED
def alias_owner_bookings():
    # مالك: عرض الحجوزات على ممتلكاتي
    return RedirectResponse(url="/bookings?view=owner", status_code=303)

# ---------- أفعال المالك ----------
@router.post("/bookings/{bid}/approve")
def booking_approve(bid: int, request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    b = db.query(Booking).get(bid)
    if not b or b.owner_id != u["id"] or b.status != "pending":
        return RedirectResponse(url="/bookings", status_code=303)
    b.status = "approved"
    db.commit()
    return RedirectResponse(url="/bookings?view=owner", status_code=303)  # >>> ADDED better back

@router.post("/bookings/{bid}/reject")
def booking_reject(bid: int, request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    b = db.query(Booking).get(bid)
    if not b or b.owner_id != u["id"] or b.status != "pending":
        return RedirectResponse(url="/bookings", status_code=303)
    b.status = "rejected"
    db.commit()
    return RedirectResponse(url="/bookings?view=owner", status_code=303)  # >>> ADDED better back

@router.post("/bookings/{bid}/complete")
def booking_complete(bid: int, request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    b = db.query(Booking).get(bid)
    if not b or b.owner_id != u["id"] or b.status != "active":
        return RedirectResponse(url="/bookings", status_code=303)
    b.status = "completed"
    db.commit()
    return RedirectResponse(url="/bookings?view=owner", status_code=303)  # >>> ADDED

# ---------- أفعال المستأجر ----------
@router.post("/bookings/{bid}/cancel")
def booking_cancel(bid: int, request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    b = db.query(Booking).get(bid)
    if not b or b.renter_id != u["id"] or b.status not in ["pending","approved"]:
        return RedirectResponse(url="/bookings", status_code=303)
    b.status = "cancelled"
    db.commit()
    return RedirectResponse(url="/bookings?view=renter", status_code=303)  # >>> ADDED

@router.post("/bookings/{bid}/activate")
def booking_activate(bid: int, request: Request, db: Session = Depends(get_db)):
    """
    المستأجر يؤكد الاستلام (بعد موافقة المالك) => active
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    b = db.query(Booking).get(bid)
    if not b or b.renter_id != u["id"] or b.status != "approved":
        return RedirectResponse(url="/bookings", status_code=303)

    today = datetime.utcnow().date()
    if today < b.start_date:
        return RedirectResponse(url="/bookings", status_code=303)

    b.status = "active"
    db.commit()
    return RedirectResponse(url="/bookings?view=renter", status_code=303)  # >>> ADDED

# ---------- NEW: API فترات محجوزة (approved/active) لعنصر ----------
@router.get("/api/items/{item_id}/booked")
def api_item_booked(item_id: int, request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(Booking)
        .filter(
            Booking.item_id == item_id,
            Booking.status.in_(["approved", "active"])
        )
        .all()
    )
    data = [
        { "start": r.start_date.isoformat(), "end": r.end_date.isoformat() }
        for r in rows
    ]
    return JSONResponse({"blocked": data})

@router.get("/bookings/{booking_id}")
def booking_detail(booking_id: int, request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    b = db.query(Booking).get(booking_id)
    if not b:
        return RedirectResponse(url="/", status_code=303)
    if u["id"] not in [b.renter_id, b.owner_id]:
        return RedirectResponse(url="/", status_code=303)

    item = db.query(Item).get(b.item_id)
    renter = db.query(User).get(b.renter_id)
    owner = db.query(User).get(b.owner_id)

    return request.app.templates.TemplateResponse(
        "booking_detail.html",
        {
            "request": request,
            "title": f"حجز #{b.id}",
            "booking": b,
            "item": item,
            "renter": renter,
            "owner": owner,
            "session_user": u,
        },
    )

def _me(request: Request):
    return request.session.get("user")

def _not_auth():
    return RedirectResponse(url="/login", status_code=303)

def _back_to_booking(bid: int):
    return RedirectResponse(url=f"/bookings/{bid}", status_code=303)

# --------- مالك يعتمد الطلب (من pending → confirmed) ----------
@router.post("/bookings/{booking_id}/confirm")
def booking_confirm(booking_id: int, request: Request, db: Session = Depends(get_db)):
    u = _me(request)
    if not u:
        return _not_auth()
    b: Booking = db.query(Booking).get(booking_id)
    if not b:
        return RedirectResponse(url="/", status_code=303)
    # فقط المالك يستطيع الاعتماد
    if u["id"] != b.owner_id or b.status != "pending":
        return _back_to_booking(booking_id)
    b.status = "confirmed"
    db.commit()
    # بعد الاعتماد → يحوّل لصفحة الدفع
    return RedirectResponse(url=f"/checkout/{booking_id}", status_code=303)

# --------- مالك يرفض الطلب (من pending → cancelled) ----------
@router.post("/bookings/{booking_id}/reject")
def booking_reject(booking_id: int, request: Request, db: Session = Depends(get_db)):
    u = _me(request)
    if not u:
        return _not_auth()
    b: Booking = db.query(Booking).get(booking_id)
    if not b:
        return RedirectResponse(url="/", status_code=303)
    if u["id"] != b.owner_id or b.status != "pending":
        return _back_to_booking(booking_id)
    b.status = "cancelled"
    db.commit()
    return _back_to_booking(booking_id)

# --------- مستأجر يلغي قبل الاعتماد ----------
@router.post("/bookings/{booking_id}/cancel")
def booking_cancel(booking_id: int, request: Request, db: Session = Depends(get_db)):
    u = _me(request)
    if not u:
        return _not_auth()
    b: Booking = db.query(Booking).get(booking_id)
    if not b:
        return RedirectResponse(url="/", status_code=303)
    # يسمح بالإلغاء إذا كان هو المستأجر والحالة pending
    if u["id"] != b.renter_id or b.status != "pending":
        return _back_to_booking(booking_id)
    b.status = "cancelled"
    db.commit()
    return _back_to_booking(booking_id)

# ================== Checkout (تجريبي) ==================
@router.get("/checkout/{booking_id}")
def checkout_page(booking_id: int, request: Request, db: Session = Depends(get_db)):
    u = _me(request)
    if not u:
        return _not_auth()
    b: Booking = db.query(Booking).get(booking_id)
    if not b:
        return RedirectResponse(url="/", status_code=303)
    if u["id"] != b.renter_id or b.status != "confirmed":
        return _back_to_booking(booking_id)
    item = db.query(Item).get(b.item_id)
    owner = db.query(User).get(b.owner_id)

    # 👇 هنا حط الـ return الجديد
    return request.app.templates.TemplateResponse(
        "checkout_detail.html",
        {
            "request": request,
            "title": f"Checkout #{b.id}",
            "booking": b,
            "item": item,
            "owner": owner,
            "session_user": u,
            "pk": os.environ.get("STRIPE_PUBLISHABLE_KEY")  # مفتاح Stripe العام
        },
    )

@router.post("/checkout/{booking_id}/pay")
def checkout_pay(booking_id: int, request: Request, db: Session = Depends(get_db)):
    u = _me(request)
    if not u:
        return _not_auth()
    b: Booking = db.query(Booking).get(booking_id)
    if not b:
        return RedirectResponse(url="/", status_code=303)
    # هنا سنحاكي نجاح الدفع
    if u["id"] == b.renter_id and b.status == "confirmed":
        b.status = "paid"
        db.commit()
    return _back_to_booking(booking_id)


@router.post("/api/checkout/{booking_id}/intent")
def api_create_intent(booking_id: int, request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u: 
        raise HTTPException(status_code=401, detail="login required")
    b: Booking = db.query(Booking).get(booking_id)
    if not b: 
        raise HTTPException(status_code=404, detail="not found")
    if u["id"] != b.renter_id: 
        raise HTTPException(status_code=403, detail="forbidden")
    if b.status not in ["confirmed", "paid"]:
        # يجب أن يكون المالك أكد الطلب (confirmed) قبل الدفع
        raise HTTPException(status_code=400, detail="not ready")

    # صاحب المنتج
    owner: User = db.query(User).get(b.owner_id)
    if not owner or not owner.stripe_account_id or not owner.payouts_enabled:
        raise HTTPException(status_code=400, detail="owner not ready for payouts")

    amount_cents = int((b.total_amount or 0) * 100)
    fee_cents = amount_cents * FEE_BPS // 10000

    # أنشئ PaymentIntent مع تحويل تلقائي إلى حساب المالك
    intent = stripe.PaymentIntent.create(
        amount = amount_cents,
        currency = "usd",
        automatic_payment_methods={"enabled": True},
        application_fee_amount = fee_cents,
        transfer_data = {"destination": owner.stripe_account_id},
        metadata = {"booking_id": str(b.id)}
    )

    b.payment_intent_id = intent["id"]
    b.payment_status = intent["status"]
    db.commit()

    return {"clientSecret": intent["client_secret"]}