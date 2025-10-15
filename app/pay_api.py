# app/pay_api.py
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional, Literal, Callable

import stripe
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, Item, User
from .notifications_api import push_notification, notify_admins

# ================= Stripe Config =================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")  # sk_test_...

# ⚠️ حدّد رابط موقعك في ENV تحت SITE_URL (بدون / في النهاية)
SITE_URL = (os.getenv("SITE_URL", "http://localhost:8000") or "").rstrip("/")

# نجعل CAD الافتراضي لضمان التطابق مع بقية النظام
CURRENCY = (os.getenv("CURRENCY", "cad") or "cad").lower()

# نسبة عمولة المنصّة (اختياري)
PLATFORM_FEE_PCT = int(os.getenv("PLATFORM_FEE_PCT", "0"))

if not stripe.api_key:
    raise RuntimeError("STRIPE_SECRET_KEY is missing in environment")

router = APIRouter(tags=["payments"])


# ================= Helpers =================
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None

def require_auth(u: Optional[User]):
    if not u:
        raise HTTPException(status_code=401, detail="Unauthorized")

def require_booking(db: Session, bid: int) -> Booking:
    bk = db.get(Booking, bid)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    return bk

def flow_redirect(bid: int) -> RedirectResponse:
    return RedirectResponse(url=f"/bookings/flow/{bid}", status_code=303)

def can_manage_deposits(u: Optional[User]) -> bool:
    """ Admin أو من لديه is_deposit_manager=True """
    if not u:
        return False
    if (getattr(u, "role", "") or "").lower() == "admin":
        return True
    return bool(getattr(u, "is_deposit_manager", False))

# توحيد قراءة/كتابة معرّف تفويض الوديعة (PI)
def _get_deposit_pi_id(bk: Booking) -> Optional[str]:
    return (
        getattr(bk, "deposit_hold_intent_id", None)
        or getattr(bk, "deposit_hold_id", None)
    )

def _set_deposit_pi_id(bk: Booking, pi_id: Optional[str]) -> None:
    try:
        setattr(bk, "deposit_hold_intent_id", pi_id)
    except Exception:
        pass
    try:
        setattr(bk, "deposit_hold_id", pi_id)
    except Exception:
        pass


# ============================================================
# (NEW) Checkout: Rent + Deposit together (same session)
# ============================================================
@router.post("/api/stripe/checkout/all/{booking_id}")
def start_checkout_all(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    إنشاء Checkout Session واحدة تشمل:
    - مبلغ الإيجار (يذهب إلى المالك عبر destination charge)
    - الوديعة (تدخل ضمن نفس الـ PaymentIntent وتُعتبر محجوزة لدينا)
    نعلّم الـ PI في الويبهوك بقيمة metadata=all.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay")
    if bk.status not in ("accepted", "requested"):
        return flow_redirect(bk.id)

    item = db.get(Item, bk.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    owner = db.get(User, bk.owner_id)
    if not owner or not getattr(owner, "stripe_account_id", None):
        raise HTTPException(status_code=400, detail="Owner is not onboarded to Stripe")

    rent_cents = int(max(0, (bk.total_amount or 0)) * 100)
    dep_cents = int(max(0, (bk.deposit_amount or getattr(bk, "hold_deposit_amount", 0) or 0)) * 100)
    if rent_cents <= 0 and dep_cents <= 0:
        return flow_redirect(bk.id)

    app_fee_cents = (rent_cents * PLATFORM_FEE_PCT) // 100 if PLATFORM_FEE_PCT > 0 else 0

    # نبني payment_intent_data بدون None
    pi_data = {
        "metadata": {"kind": "all", "booking_id": str(bk.id)},
        "transfer_data": {"destination": owner.stripe_account_id},
    }
    if app_fee_cents > 0:
        pi_data["application_fee_amount"] = app_fee_cents

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_intent_data=pi_data,
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": CURRENCY,
                        "product_data": {"name": f"Rent for '{item.title}' (#{bk.id})"},
                        "unit_amount": rent_cents,
                    },
                },
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": CURRENCY,
                        "product_data": {"name": f"Deposit for '{item.title}' (#{bk.id})"},
                        "unit_amount": dep_cents,
                    },
                },
            ],
            success_url=f"{SITE_URL}/bookings/flow/{bk.id}?all_ok=1&sid={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{SITE_URL}/bookings/flow/{bk.id}?cancel=1",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")

    bk.payment_method = "online"
    bk.online_status = "pending_authorization"
    db.commit()
    return RedirectResponse(url=session.url, status_code=303)


# ============ (A) Stripe Connect Onboarding ============
@router.post("/api/stripe/connect/start")
def connect_start(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يبدأ إنشاء/إكمال حساب Stripe Connect للمالك.
    - إن لم يوجد stripe_account_id ننشئ Account (Express).
    - ننشئ AccountLink للتحويل إلى صفحة Stripe.
    """
    require_auth(user)

    if not getattr(user, "stripe_account_id", None):
        try:
            account = stripe.Account.create(type="express")
            user.stripe_account_id = account.id
            db.commit()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Stripe create account failed: {e}")

    try:
        link = stripe.AccountLink.create(
            account=user.stripe_account_id,
            refresh_url=f"{SITE_URL}/payouts/refresh",
            return_url=f"{SITE_URL}/payouts/return",
            type="account_onboarding",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe account link failed: {e}")

    return RedirectResponse(url=link.url, status_code=303)


@router.get("/api/stripe/connect/status")
def connect_status(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يجلب حالة حساب المالك من Stripe ويحدّث payouts_enabled في قاعدة البيانات.
    """
    require_auth(user)
    if not getattr(user, "stripe_account_id", None):
        return JSONResponse({"connected": False, "payouts_enabled": False, "reason": "no_account"})

    try:
        acc = stripe.Account.retrieve(user.stripe_account_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe retrieve account failed: {e}")

    old_enabled = bool(getattr(user, "payouts_enabled", False))
    now_enabled = bool(acc.get("payouts_enabled", False))
    user.payouts_enabled = now_enabled
    db.commit()

    return JSONResponse({
        "connected": True,
        "payouts_enabled": now_enabled,
        "previous": old_enabled,
        "details_submitted": acc.get("details_submitted", False),
        "charges_enabled": acc.get("charges_enabled", False),
        "capabilities": acc.get("capabilities", {}),
    })


# ============ (B) Checkout: Rent فقط (manual capture + destination) ============
@router.post("/api/stripe/checkout/rent/{booking_id}")
def start_checkout_rent(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    - يُنشئ Session لتفويض مبلغ الإيجار (capture لاحقًا عند الاستلام).
    - تحويل الوجهة لحساب المالك عبر transfer_data.destination (Destination Charge).
    - تطبيق عمولة المنصّة application_fee_amount إن وُجدت.
    - بعد نجاح الـ Checkout، webhook يحدّث الحجز إلى paid ويخزن payment_intent_id.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay")
    if bk.status not in ("accepted", "requested"):
        return flow_redirect(bk.id)

    item = db.get(Item, bk.item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    owner = db.get(User, bk.owner_id)
    if not owner or not getattr(owner, "stripe_account_id", None):
        raise HTTPException(status_code=400, detail="Owner is not onboarded to Stripe")

    amount_cents = int(max(0, (bk.total_amount or 0)) * 100)
    app_fee_cents = (amount_cents * PLATFORM_FEE_PCT) // 100 if PLATFORM_FEE_PCT > 0 else 0

    pi_data: dict = {
        "capture_method": "manual",
        "metadata": {"kind": "rent", "booking_id": str(bk.id)},
        "transfer_data": {"destination": owner.stripe_account_id},
    }
    if app_fee_cents > 0:
        pi_data["application_fee_amount"] = app_fee_cents

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_intent_data=pi_data,
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": CURRENCY,
                    "product_data": {"name": f"Rent for '{item.title}' (#{bk.id})"},
                    "unit_amount": amount_cents,
                },
            }],
            success_url=f"{SITE_URL}/bookings/flow/{bk.id}?rent_ok=1&sid={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{SITE_URL}/bookings/flow/{bk.id}?cancel=1",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")

    bk.payment_method = "online"
    bk.online_status = "pending_authorization"
    db.commit()
    return RedirectResponse(url=session.url, status_code=303)


# ============ (C) Checkout: Deposit فقط (manual capture, no transfer) ============
@router.post("/api/stripe/checkout/deposit/{booking_id}")
def start_checkout_deposit(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يُنشئ Session لتفويض الديبو (hold) بدون تحويل. القرار لاحقًا عبر resolve_deposit.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay deposit")

    dep = int(max(0, bk.deposit_amount or getattr(bk, "hold_deposit_amount", 0) or 0))
    if dep <= 0:
        return flow_redirect(bk.id)

    item = db.get(Item, bk.item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_intent_data={
                "capture_method": "manual",
                "metadata": {"kind": "deposit", "booking_id": str(bk.id)},
            },
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": CURRENCY,
                    "product_data": {"name": f"Deposit hold for '{item.title}' (#{bk.id})"},
                    "unit_amount": dep * 100,
                },
            }],
            success_url=f"{SITE_URL}/bookings/flow/{bk.id}?deposit_ok=1&sid={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{SITE_URL}/bookings/flow/{bk.id}?cancel=1",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")

    if not bk.online_status:
        bk.online_status = "pending_authorization"
    db.commit()
    return RedirectResponse(url=session.url, status_code=303)


# ============ (D) Webhook: تثبيت نتائج Checkout ============
def _handle_checkout_completed(session_obj: dict, db: Session) -> None:
    """منطق المعالجة الفعلي للويبهوك (نستدعيه من مسارين)."""
    intent_id = session_obj.get("payment_intent")
    pi = stripe.PaymentIntent.retrieve(intent_id) if intent_id else None
    md = (pi.metadata or {}) if pi else {}
    kind = md.get("kind")
    booking_id = int(md.get("booking_id") or 0)

    bk = db.get(Booking, booking_id) if booking_id else None
    if not bk:
        return

    if kind == "rent":
        bk.online_payment_intent_id = pi.id
        bk.online_status = "authorized"
        bk.status = "paid"
        bk.timeline_paid_at = datetime.utcnow()
        db.commit()
        push_notification(db, bk.owner_id, "تم تفويض دفعة الإيجار",
                          f"حجز #{bk.id}: التفويض جاهز. سلّم الغرض عند الموعد.",
                          f"/bookings/flow/{bk.id}", "booking")
        push_notification(db, bk.renter_id, "تم تفويض دفعتك",
                          f"حجز #{bk.id}. يمكنك استلام الغرض الآن.",
                          f"/bookings/flow/{bk.id}", "booking")

    elif kind == "deposit":
        _set_deposit_pi_id(bk, pi.id)
        bk.deposit_status = "held"
        db.commit()
        push_notification(db, bk.owner_id, "تم حجز الديبو",
                          f"حجز #{bk.id}: الديبو محجوز.",
                          f"/bookings/flow/{bk.id}", "deposit")
        push_notification(db, bk.renter_id, "تم حجز الديبو",
                          f"حجز #{bk.id}: الديبو الآن محجوز.",
                          f"/bookings/flow/{bk.id}", "deposit")

    elif kind == "all":
        # دفع الإيجار + اعتبار الوديعة محجوزة على نفس الـ PI
        bk.online_payment_intent_id = pi.id
        _set_deposit_pi_id(bk, pi.id)
        bk.online_status = "authorized"
        bk.deposit_status = "held"
        bk.status = "paid"
        bk.timeline_paid_at = datetime.utcnow()
        db.commit()
        push_notification(db, bk.owner_id, "تم الدفع الكامل",
                          f"حجز #{bk.id}: تم دفع الإيجار وحجز الوديعة معًا.",
                          f"/bookings/flow/{bk.id}", "booking")
        push_notification(db, bk.renter_id, "تم الدفع بنجاح",
                          f"تم دفع الإيجار والوديعة معًا لحجز #{bk.id}.",
                          f"/bookings/flow/{bk.id}", "booking")


def _webhook_handler_factory() -> Callable:
    async def _handler(request: Request, db: Session = Depends(get_db)):
        payload = await request.body()
        sig = request.headers.get("stripe-signature")
        endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        try:
            event = stripe.Webhook.construct_event(payload, sig, endpoint_secret)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        if event["type"] == "checkout.session.completed":
            _handle_checkout_completed(event["data"]["object"], db)

        # يمكن إضافة معالجات لأحداث أخرى إذا لزم
        return JSONResponse({"ok": True})
    return _handler

# ندعم مسارين تجنبًا لاختلاف الإعدادات بين الكود ولوحة Stripe
router.post("/webhooks/stripe")(_webhook_handler_factory())
router.post("/stripe/webhook")(_webhook_handler_factory())


# ============ (E) التقاط مبلغ الإيجار يدويًا ============
@router.post("/api/stripe/capture-rent/{booking_id}")
def capture_rent(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يلتقط مبلغ الإيجار المُفوّض ويرسله لحساب المالك.
    عادة نربطه بزر "تم الاستلام".
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not getattr(bk, "online_payment_intent_id", None):
        return flow_redirect(bk.id)

    try:
        stripe.PaymentIntent.capture(bk.online_payment_intent_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe capture failed: {e}")

    bk.payment_status = "released"
    bk.online_status = "captured"
    bk.rent_released_at = datetime.utcnow()
    db.commit()
    push_notification(db, bk.owner_id, "تم تحويل مبلغ الإيجار",
                      f"حجز #{bk.id}: تم تحويل المبلغ لك.",
                      f"/bookings/flow/{bk.id}", "booking")
    return flow_redirect(bk.id)


# ============ (F) قرار الوديعة: Admin/Deposit Manager ============
@router.post("/api/stripe/deposit/resolve/{booking_id}")
def resolve_deposit(
    booking_id: int,
    action: Literal["refund_all", "withhold_partial", "withhold_all"] = Form(...),
    partial_amount: int = Form(0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    بعد الإرجاع:
      - refund_all        : إلغاء التفويض بالكامل.
      - withhold_all      : اقتطاع كامل الديبو لصالح المالك.
      - withhold_partial  : اقتطاع جزء من الديبو.
    متاح فقط لمن لديه صلاحية (Admin أو Deposit Manager).
    """
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Deposit decision requires Admin or Deposit Manager")

    bk = require_booking(db, booking_id)
    pi_id = _get_deposit_pi_id(bk)
    if not pi_id:
        # لا يوجد تفويض وديعة محفوظ
        return flow_redirect(bk.id)

    dep = int(max(0, bk.deposit_amount or getattr(bk, "hold_deposit_amount", 0) or 0))
    try:
        if action == "refund_all":
            # إلغاء التفويض بالكامل (لا سحب)
            stripe.PaymentIntent.cancel(pi_id)
            bk.deposit_status = "refunded"
            bk.deposit_charged_amount = 0

        elif action == "withhold_all":
            # اقتطاع كامل الديبو
            stripe.PaymentIntent.capture(pi_id, amount_to_capture=dep * 100)
            bk.deposit_status = "claimed"
            bk.deposit_charged_amount = dep

        elif action == "withhold_partial":
            amt = int(max(0, partial_amount or 0))
            if amt <= 0 or amt >= dep:
                raise HTTPException(status_code=400, detail="Invalid partial amount")
            stripe.PaymentIntent.capture(pi_id, amount_to_capture=amt * 100)
            bk.deposit_status = "partially_withheld"
            # قد يكون لدينا اقتطاعات سابقة؛ نجمعها بشكل آمن
            prev = int(getattr(bk, "deposit_charged_amount", 0) or 0)
            bk.deposit_charged_amount = prev + amt

        else:
            raise HTTPException(status_code=400, detail="Unknown action")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe deposit op failed: {e}")

    db.commit()

    # إشعارات (اختياري)
    notify_admins(db, "تم تنفيذ قرار وديعة", f"حجز #{bk.id}: {action}.", f"/bookings/flow/{bk.id}")
    push_notification(db, bk.owner_id, "قرار الوديعة",
                      f"تم تنفيذ القرار: {action}.", f"/bookings/flow/{bk.id}", "deposit")
    push_notification(db, bk.renter_id, "قرار الوديعة",
                      f"تم تنفيذ القرار: {action}.", f"/bookings/flow/{bk.id}", "deposit")

    return flow_redirect(bk.id)