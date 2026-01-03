from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime, date, timedelta
import os

from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from .database import get_db
from .models import User, Item, Booking, UserReview
from .utils import category_label, display_currency, fx_convert
from .notifications_api import push_notification, notify_admins
from .pay_api import paypal_start, paypal_return, compute_grand_total_for_paypal

# ✅ ADDITIONS
from .utili_geo import locate_from_session
from .utili_tax import compute_order_taxes

from fastapi import BackgroundTasks
from .database import SessionLocal

router = APIRouter(tags=["bookings"])

DISPUTE_WINDOW_HOURS = 48
RENTER_REPLY_WINDOW_HOURS = 48

# =====================================================
# Auth helpers
# =====================================================
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
    return user.id == bk.renter_id

def is_owner(user: User, bk: Booking) -> bool:
    return user.id == bk.owner_id

def redirect_to_flow(bk: Booking):
    return RedirectResponse(url=f"/bookings/flow/{bk.id}", status_code=303)

@router.post("/bookings")
async def create_booking(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)

    form = await request.form()

    item_id_raw = form.get("item_id")
    start_raw   = form.get("start_date")
    end_raw     = form.get("end_date")

    if not item_id_raw or not start_raw or not end_raw:
        raise HTTPException(status_code=400, detail="Missing booking data")

    try:
        item_id    = int(item_id_raw)
        start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
        end_date   = datetime.strptime(end_raw, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking data")

    if end_date <= start_date:
        raise HTTPException(status_code=400, detail="Invalid dates")

    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=400, detail="Invalid item")

    days = max(1, (end_date - start_date).days)
    total_amount = days * item.price_per_day

    bk = Booking(
        item_id=item.id,
        renter_id=user.id,
        owner_id=item.owner_id,
        start_date=start_date,
        end_date=end_date,
        days=days,
        price_per_day_snapshot=item.price_per_day,
        total_amount=total_amount,
        status="requested",

        payment_provider="paypal",
        payment_status="pending",
        online_status="created",

        platform_fee=0,
        rent_amount=total_amount,
        hold_deposit_amount=0,
        owner_payout_amount=0,
        deposit_amount=0,
        deposit_charged_amount=0,
        amount_native=total_amount,
        amount_display=total_amount,
        amount_paid_cents=0,

        rent_paid=False,
        security_paid=False,
        security_amount=0,
        security_status="not_paid",
        refund_done=False,
        payout_executed=False,
        owner_due_amount=0,

        timeline_created_at=datetime.utcnow(),
    )

    db.add(bk)
    db.commit()
    db.refresh(bk)

    # ✅ كل شيء ثقيل بالخلفية (إشعار + إيميل)
    background_tasks.add_task(_after_booking_created_bg, bk.id)

    # ✅ Redirect فوري (هذا اللي يخلي الزر سريع)
    return redirect_to_flow(bk)


def _after_booking_created_bg(booking_id: int):
    db = SessionLocal()
    try:
        bk = db.get(Booking, booking_id)
        if not bk:
            return

        item = db.get(Item, bk.item_id)
        owner = db.get(User, bk.owner_id)
        renter = db.get(User, bk.renter_id)

        # 🔔 إشعار داخل الموقع للمالك
        try:
            push_notification(
                db,
                bk.owner_id,
                "New booking request",
                f"Request on '{item.title}'.",
                f"/bookings/flow/{bk.id}",
                "booking",
            )
        except Exception as e:
            print("PUSH ERROR (BG CREATE BOOKING):", e)

        # 📧 EMAIL — OWNER (نفس الإيميل القديم)
        try:
            from .email_service import send_email

            if owner and owner.email:
                subject = f"New booking request — Booking #{bk.id}"
                msg_txt = f"You received a new booking request for '{item.title}'."
                html = f"""
                <div style="font-family:Arial">
                    <h2>New booking request</h2>
                    <p><b>Item:</b> {item.title}</p>
                    <p><b>Renter:</b> {renter.first_name if renter else ''}</p>
                    <a href="https://sevor.net/bookings/flow/{bk.id}">
                        Open booking
                    </a>
                </div>
                """

                send_email(
                    to=owner.email,
                    subject=subject,
                    text_body=msg_txt,
                    html_body=html,
                )
        except Exception as e:
            print("EMAIL ERROR (BG CREATE BOOKING):", e)

    finally:
        db.close()

@router.get("/bookings/flow/{booking_id}")
def booking_flow(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    item = db.get(Item, bk.item_id)
    owner = db.get(User, bk.owner_id)
    renter = db.get(User, bk.renter_id)

    # Reviews count
    renter_reviews_count = (
        db.query(UserReview)
        .filter(UserReview.owner_id == renter.id)
        .count()
    )

    # Geo
    geo = locate_from_session(request)
    if not isinstance(geo, dict):
        geo = {}

    # ============================
    # 💰 PRICING — SOURCE UNIQUE
    # ============================
    pricing = compute_grand_total_for_paypal(request, bk)

    # ============================
    # ⏱️ DISPUTE DEADLINE (TEST MODE = 1 MINUTE)
    # ============================
    dispute_deadline_iso = None
    if bk.returned_at:
        # ⛔ TEST فقط: دقيقة واحدة
        dispute_deadline = bk.returned_at + timedelta(hours=24)

        dispute_deadline = dispute_deadline.replace(microsecond=0)

        dispute_deadline_iso = dispute_deadline.isoformat() + "Z"

    # ============================
    # 📦 CONTEXT
    # ============================
    ctx = {
        "request": request,
        "booking": bk,
        "item": item,
        "owner": owner,
        "renter": renter,
        "is_owner": is_owner(user, bk),
        "is_renter": is_renter(user, bk),
        "category_label": category_label,

        # 💰 AMOUNTS (FROM SINGLE SOURCE)
        "rent": pricing["rent"],
        "sevor_fee": pricing["sevor_fee"],
        "paypal_fee": pricing["paypal_fee"],
        "grand_total": pricing["grand_total"],

        # taxes disabled
        "tax_lines": [],
        "tax_total": 0.0,

        "geo": geo,
        "session_user": request.session.get("user"),
        "renter_reviews_count": renter_reviews_count,

        # ⏱️ PASS DEADLINE TO TEMPLATE
        "dispute_deadline_iso": dispute_deadline_iso,
    }

    return request.app.templates.TemplateResponse("booking_flow.html", ctx)


@router.post("/bookings/{booking_id}/owner/decision")
def owner_decision_route(
    booking_id: int,
    decision: Literal["accepted", "rejected"] = Form(...),
    deposit_amount: float = Form(0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if not is_owner(user, bk):
        raise HTTPException(status_code=403)

    renter = db.get(User, bk.renter_id)
    item = db.get(Item, bk.item_id)

    # =========================
    # ❌ REJECTED
    # =========================
    if decision == "rejected":
        bk.status = "rejected"
        bk.rejected_at = datetime.utcnow()
        db.commit()

        # 📧 EMAIL — RENTER (REJECTED)
        try:
            from .email_service import send_email
            if renter and renter.email:
                send_email(
                    to=renter.email,
                    subject="Booking rejected",
                    text_body=f"Your booking for '{item.title}' was rejected.",
                    html_body=f"""
                    <h2>Booking rejected</h2>
                    <p>Your request for <b>{item.title}</b> was rejected.</p>
                    """
                )
        except Exception as e:
            print("EMAIL ERROR (REJECTED):", e)

        return redirect_to_flow(bk)

    # =========================
    # ✅ ACCEPTED
    # =========================
    bk.status = "accepted"
    bk.accepted_at = datetime.utcnow()
    bk.security_amount = deposit_amount
    bk.deposit_amount = int(deposit_amount)
    bk.hold_deposit_amount = int(deposit_amount)

    db.commit()
    db.refresh(bk)

    push_notification(
        db,
        bk.renter_id,
        "Booking accepted",
        "Please complete payment via PayPal.",
        f"/bookings/flow/{bk.id}",
        "booking",
    )

    # 📧 EMAIL — RENTER (ACCEPTED)
    try:
        from .email_service import send_email
        if renter and renter.email:
            send_email(
                to=renter.email,
                subject="Booking accepted 🎉",
                text_body=f"Your booking for '{item.title}' was accepted.",
                html_body=f"""
                <div style="font-family:Arial">
                    <h2>Booking accepted 🎉</h2>
                    <p><b>Item:</b> {item.title}</p>
                    <p><b>Deposit:</b> {bk.deposit_amount}$</p>
                    <a href="https://sevor.net/bookings/flow/{bk.id}">
                        Continue booking
                    </a>
                </div>
                """
            )
    except Exception as e:
        print("EMAIL ERROR (ACCEPTED):", e)

    return redirect_to_flow(bk)

# =====================================================
# Pickup
# =====================================================
@router.post("/bookings/{booking_id}/pickup")
def renter_pickup(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403)

    if bk.status != "paid":
        raise HTTPException(status_code=400)

    bk.status = "picked_up"
    bk.picked_up_at = datetime.utcnow()
    db.commit()

    return redirect_to_flow(bk)

# =====================================================
# Return
# =====================================================
@router.post("/bookings/{booking_id}/return")
def renter_return(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_renter(user, bk):
        raise HTTPException(status_code=403)

    bk.status = "returned"
    bk.returned_at = datetime.utcnow()
    db.commit()

    notify_admins(
        db,
        "Deposit review required",
        f"Booking #{bk.id} requires deposit decision.",
        f"/bookings/flow/{bk.id}",
    )

    return redirect_to_flow(bk)

# =====================================================
# Booking index
# =====================================================
@router.get("/bookings")
def bookings_index(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    view: Literal["renter", "owner"] = "renter",
):
    require_auth(user)

    if view == "owner":
        bookings = db.query(Booking).filter(Booking.owner_id == user.id).all()
    else:
        bookings = db.query(Booking).filter(Booking.renter_id == user.id).all()

    return request.app.templates.TemplateResponse(
        "booking_index.html",
        {
            "request": request,
            "bookings": bookings,
            "view": view,
            "user": user,
        },
    )

# ========================================
# UI: Create page
# ========================================
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

    item_cur = (item.currency or "CAD").upper()
    disp_cur = display_currency(request)

    today = date.today()
    ctx = {
        "request": request,
        "user": user,
        "session_user": request.session.get("user"),
        "display_currency": disp_cur,
        "item": item,
        "disp_price": item.price_per_day,
        "item_currency": item_cur,
        "start_default": today,
        "end_default": today + timedelta(days=1),
        "days_default": 1,
    }

    return request.app.templates.TemplateResponse("booking_new.html", ctx)

@router.post("/bookings/{booking_id}/renter/confirm_received")
def renter_confirm_received(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    # renter only
    if not is_renter(user, bk):
        raise HTTPException(status_code=403, detail="Only renter can confirm")

    # Valid states
    if bk.status not in (
        "paid",
        "awaiting_pickup",
        "accepted",
        "pending_payment",
        "in_use",
        "authorized",
        "captured",
        "paid_online",
        "ready_for_pickup",
        "picked_up",
    ):
        raise HTTPException(status_code=400, detail="Invalid state")

    item = db.get(Item, bk.item_id)

    # ==============================
    # تحديث حالة الحجز
    # ==============================
    bk.status = "picked_up"
    bk.picked_up_at = datetime.utcnow()
    bk.timeline_renter_received_at = datetime.utcnow()

    # =====================================================
    # ✅ ADD — PREPARE PAYOUT FOR ADMIN (بدون حذف أي شيء)
    # =====================================================

    # 1️⃣ حساب مبلغ المالك (الإيجار − عمولة المنصة)
    rent_amount = float(bk.rent_amount or 0)
    platform_fee = float(bk.platform_fee or 0)

    owner_amount = rent_amount - platform_fee
    if owner_amount < 0:
        owner_amount = 0

    bk.owner_amount = owner_amount
    bk.owner_due_amount = owner_amount

    # 2️⃣ تعليم الحجز كجاهز للدفع في لوحة الأدمن
    bk.payout_ready = True
    bk.payout_sent = False
    

    # 3️⃣ حالة طلب الدفع
    bk.owner_payout_request = True
    bk.owner_payout_status = "waiting_admin"
    bk.owner_payout_attempts = 0
    bk.owner_payout_last_try_at = None

    # =====================================================
    # 🔥 لا ترسل أموال تلقائياً — فقط أرسل إلى Admin
    # =====================================================

    db.commit()

    # ==============================
    # PUSH NOTIFICATIONS
    # ==============================
    if item:
        # إشعار للمالك
        push_notification(
            db,
            bk.owner_id,
            "Renter picked up the item",
            f"'{item.title}'. Your payout is pending admin approval.",
            f"/bookings/flow/{bk.id}",
            "booking",
        )

        # إشعار للمستأجر
        push_notification(
            db,
            bk.renter_id,
            "Pickup confirmed",
            f"You picked up '{item.title}'.",
            f"/bookings/flow/{bk.id}",
            "booking",
        )

        # 🔔 إشعار للأدمن (مهم جداً لصفحة payouts)
        notify_admins(
            db,
            "Payout ready",
            f"Booking #{bk.id} is ready for owner payout.",
            f"/admin/payouts",
        )

    # ===========================================
    # EMAIL — Owner (Renter picked up the item)
    # ===========================================
    try:
        from .email_service import send_email
        owner_user = db.get(User, bk.owner_id)
        renter_user = db.get(User, bk.renter_id)

        if owner_user and owner_user.email:
            subject = f"Renter picked up your item — Booking #{bk.id}"
            msg_txt = (
                f"The renter '{renter_user.first_name if renter_user else ''}' "
                f"picked up your item '{item.title}'. "
                f"Your payout is now pending admin approval."
            )

            html = f"""
            <div style='font-family:Arial,Helvetica,sans-serif; line-height:1.6; color:#111;'>
                <h2 style="color:#16a34a;">Item picked up</h2>
                <p>{msg_txt}</p>
                <p>
                    <a href="https://sevor.net/bookings/flow/{bk.id}"
                       style="padding:12px 18px; background:#16a34a; color:white;
                              border-radius:8px; text-decoration:none;">
                        Open booking
                    </a>
                </p>
            </div>
            """

            send_email(
                to=owner_user.email,
                subject=subject,
                html_body=html,
                text_body=msg_txt,
            )

    except Exception as e:
        print("EMAIL ERROR (OWNER PICKED UP):", e)

    # ===========================================
    # EMAIL — Renter (Pickup confirmed)
    # ===========================================
    try:
        from .email_service import send_email
        renter_user = db.get(User, bk.renter_id)

        if renter_user and renter_user.email:
            subject = f"Pickup confirmed — Booking #{bk.id}"
            msg_txt = (
                f"You picked up '{item.title}'. "
                f"Enjoy your rental!"
            )

            html = f"""
            <div style='font-family:Arial,Helvetica,sans-serif; line-height:1.6; color:#111;'>
                <h2 style="color:#2563eb;">Pickup confirmed</h2>
                <p>{msg_txt}</p>
                <p>
                    <a href="https://sevor.net/bookings/flow/{bk.id}"
                       style="padding:12px 18px; background:#2563eb; color:white;
                              border-radius:8px; text-decoration:none;">
                        View booking
                    </a>
                </p>
            </div>
            """

            send_email(
                to=renter_user.email,
                subject=subject,
                html_body=html,
                text_body=msg_txt,
            )

    except Exception as e:
        print("EMAIL ERROR (RENTER PICKUP CONFIRMED):", e)

    renter = db.get(User, bk.renter_id)
    return redirect_to_flow(bk)

    # ===========================================
    # EMAIL — Renter (Pickup confirmed)
    # ===========================================
    try:
        from .email_service import send_email
        renter_user = db.get(User, bk.renter_id)

        if renter_user and renter_user.email:
            subject = f"Pickup confirmed — Booking #{bk.id}"
            title_txt = "Enjoy your rental! 🎉"
            msg_txt = (
                f"You picked up '{item.title}'. Make sure to return it on time "
                f"to avoid any extra charges."
            )

            html = f"""
            <div style='font-family:Arial,Helvetica,sans-serif; line-height:1.6; color:#111;'>
                <img src="https://sevor.net/static/img/sevor-logo.png"
                     style="width:120px; margin-bottom:20px;" />

                <h2 style="color:#2563eb;">{title_txt}</h2>
                <p>{msg_txt}</p>

                <p>
                    <a href="https://sevor.net/bookings/flow/{bk.id}"
                       style="padding:12px 18px; background:#2563eb; color:white;
                              border-radius:8px; text-decoration:none; display:inline-block;">
                        View booking details
                    </a>
                </p>

                <br>
                <p style='color:#888;'>Sevor — Rent anything worldwide</p>
            </div>
            """

            send_email(
                to=renter_user.email,
                subject=subject,
                html_body=html,
                text_body=msg_txt,
            )

    except Exception as e:
        print("EMAIL ERROR (RENTER PICKUP CONFIRMED):", e)

    renter = db.get(User, bk.renter_id)
    return redirect_to_flow_with_loc(bk, renter)




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

    # ======================
    # PUSH NOTIFICATIONS
    # ======================
    push_notification(
        db, bk.owner_id, "Return marked",
        f"The item '{item.title}' was returned. Waiting for admin review of the deposit.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    push_notification(
        db, bk.renter_id, "Deposit under review",
        f"You will be notified after the admin reviews the deposit for booking '{item.title}'.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    notify_admins(
        db, "Deposit review required",
        f"Booking #{bk.id} needs a deposit decision.",
        f"/bookings/flow/{bk.id}"
    )

    # ===========================================
    # EMAIL — Owner (item returned)
    # ===========================================
    try:
        from .email_service import send_email
        owner_user = db.get(User, bk.owner_id)
        renter_user = db.get(User, bk.renter_id)

        if owner_user and owner_user.email:
            subject = f"Item returned — Booking #{bk.id}"
            msg_txt = (
                f"The renter '{renter_user.first_name if renter_user else 'User'}' "
                f"marked the item '{item.title}' as returned. "
                f"The deposit is now waiting for admin review."
            )

            html = f"""
            <div style='font-family:Arial,Helvetica,sans-serif; line-height:1.6; color:#111;'>
                <img src="https://sevor.net/static/img/sevor-logo.png"
                     style="width:140px; margin-bottom:20px;" />

                <h2 style="color:#16a34a;">Item marked as returned</h2>

                <p>The renter has marked your item as returned:</p>

                <p><b>Item:</b> {item.title}</p>
                <p><b>Renter:</b> {renter_user.first_name if renter_user else 'User'}</p>

                <p>The deposit is now under review by the Sevor team.</p>

                <p>
                    <a href="https://sevor.net/bookings/flow/{bk.id}"
                       style="padding:12px 18px; background:#16a34a; color:white;
                              text-decoration:none; border-radius:8px; display:inline-block;">
                        Open booking
                    </a>
                </p>

                <br>
                <p style='color:#888;font-size:13px;'>Sevor — Rent anything worldwide</p>
            </div>
            """

            send_email(
                to=owner_user.email,
                subject=subject,
                html_body=html,
                text_body=msg_txt,
            )

    except Exception as e:
        print("EMAIL ERROR (RETURN MARKED OWNER):", e)

    # ===========================================
    # EMAIL — Renter (deposit under review)
    # ===========================================
    try:
        from .email_service import send_email
        renter_user = db.get(User, bk.renter_id)

        if renter_user and renter_user.email:
            subject = f"Deposit under review — Booking #{bk.id}"
            title_txt = "Your deposit is under review"
            msg_txt = (
                f"You marked '{item.title}' as returned. "
                f"Our team will review the deposit and notify you once a decision is made."
            )

            html = f"""
            <div style='font-family:Arial,Helvetica,sans-serif; line-height:1.6; color:#111;'>
                <img src="https://sevor.net/static/img/sevor-logo.png"
                     style="width:140px; margin-bottom:20px;" />

                <h2 style="color:#f97316;">{title_txt}</h2>

                <p>{msg_txt}</p>

                <p>
                    <a href="https://sevor.net/bookings/flow/{bk.id}"
                       style="padding:12px 18px; background:#f97316; color:white;
                              text-decoration:none; border-radius:8px; display:inline-block;">
                        View booking details
                    </a>
                </p>

                <br>
                <p style='color:#888;font-size:13px;'>Sevor — Rent anything worldwide</p>
            </div>
            """

            send_email(
                to=renter_user.email,
                subject=subject,
                html_body=html,
                text_body=msg_txt,
            )

    except Exception as e:
        print("EMAIL ERROR (RETURN MARKED RENTER):", e)

    return _redir(bk.id)

