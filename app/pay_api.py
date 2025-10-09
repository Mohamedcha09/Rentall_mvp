# app/pay_api.py
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional, Literal

import stripe
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, Item, User
from .notifications_api import push_notification

# ========= إعداد Stripe =========
# استخدم مفاتيح الاختبار التي زوّدتني بها (sk_test/pk_test) في .env
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")
# عملتك من .env (أنت ضبطتها إلى CAD)
CURRENCY = (os.getenv("CURRENCY", "usd") or "usd").lower()
# نسبة عمولة المنصة (اختياري)
PLATFORM_FEE_PCT = int(os.getenv("PLATFORM_FEE_PCT", "0"))

if not stripe.api_key:
    raise RuntimeError("STRIPE_SECRET_KEY is missing")

router = APIRouter(tags=["payments"])


# ========= Helpers =========
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

# --- (NEW) السماح للأدمِن أو لمتحكّم الوديعة ---
def can_manage_deposits(u: Optional[User]) -> bool:
    if not u:
        return False
    role = (getattr(u, "role", "") or "").lower()
    if role == "admin":
        return True
    return bool(getattr(u, "is_deposit_manager", False))


# ========= (A) Stripe Connect Onboarding للمالك =========
@router.post("/api/stripe/connect/start")
def connect_start(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يبدأ رحلة إنشاء/إكمال حساب Stripe Connect (Express/Standard).
    - إذا لا يوجد stripe_account_id للمستخدم → ننشئ account.
    - ننشئ AccountLink ونحوّل المالك إلى صفحة Stripe لإكمال البيانات.
    """
    require_auth(user)

    # 1) أنشئ حساب لو مفقود
    if not getattr(user, "stripe_account_id", None):
        try:
            # اختر نوع الحساب المناسب. الافتراضي هنا "express".
            account = stripe.Account.create(type="express")
            user.stripe_account_id = account.id
            db.commit()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Stripe create account failed: {e}")

    # 2) أنشئ رابط الـ onboarding
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
    يجلب حالة حساب المالك من Stripe ويحفظ payouts_enabled في قاعدة البيانات.
    استدعِه بعد الرجوع من onboarding أو من صفحة الإعدادات.
    """
    require_auth(user)
    if not getattr(user, "stripe_account_id", None):
        return JSONResponse({"connected": False, "payouts_enabled": False, "reason": "no_account"}, status_code=200)

    try:
        acc = stripe.Account.retrieve(user.stripe_account_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe retrieve account failed: {e}")

    was_enabled = bool(getattr(user, "payouts_enabled", False))
    now_enabled = bool(acc.get("payouts_enabled", False))
    user.payouts_enabled = now_enabled
    db.commit()

    return JSONResponse({
        "connected": True,
        "payouts_enabled": now_enabled,
        "previous": was_enabled,
        "capabilities": acc.get("capabilities", {}),
        "details_submitted": acc.get("details_submitted", False),
        "charges_enabled": acc.get("charges_enabled", False),
    })


# ========= (B) Checkout للإيجار (تفويض فقط) =========
@router.post("/api/stripe/checkout/rent/{booking_id}")
def start_checkout_rent(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    - يفوِّض مبلغ الإيجار (manual capture).
    - يحدد التحويل إلى حساب المالك عبر transfer_data.destination (Destination charge).
    - تُطبّق عمولة المنصة (application_fee_amount) إن كانت > 0.
    - بعد نجاح الـ Checkout → webhook يغيّر الحجز إلى paid ويخزن الـ payment_intent_id.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay")
    if bk.status not in ("accepted", "requested"):
        return flow_redirect(bk.id)

    item = db.get(Item, bk.item_id) or (_ for _ in ()).throw(HTTPException(404, "Item not found"))
    owner = db.get(User, bk.owner_id)
    if not owner or not getattr(owner, "stripe_account_id", None):
        raise HTTPException(status_code=400, detail="Owner is not onboarded to Stripe (missing stripe_account_id)")

    amount_cents = max(0, (bk.total_amount or 0)) * 100
    app_fee_cents = (amount_cents * PLATFORM_FEE_PCT) // 100 if PLATFORM_FEE_PCT > 0 else 0

    pid: dict = {
        "capture_method": "manual",
        "metadata": {"kind": "rent", "booking_id": str(bk.id)},
        "transfer_data": {"destination": owner.stripe_account_id},
    }
    if app_fee_cents > 0:
        pid["application_fee_amount"] = app_fee_cents

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_intent_data=pid,
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


# ========= (C) Checkout للديبو (تفويض فقط) =========
@router.post("/api/stripe/checkout/deposit/{booking_id}")
def start_checkout_deposit(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يفوِّض مبلغ الديبو (manual capture). لا يوجد تحويل هنا.
    لاحقاً نقرر عبر /api/stripe/deposit/resolve/{booking_id}.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay deposit")

    dep = max(0, bk.deposit_amount or bk.hold_deposit_amount or 0)
    if dep <= 0:
        return flow_redirect(bk.id)

    item = db.get(Item, bk.item_id) or (_ for _ in ()).throw(HTTPException(404, "Item not found"))
    amount_cents = dep * 100

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
                    "unit_amount": amount_cents,
                },
            }],
            success_url=f"{SITE_URL}/bookings/flow/{bk.id}?deposit_ok=1&sid={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{SITE_URL}/bookings/flow/{bk.id}?cancel=1",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")

    bk.online_status = bk.online_status or "pending_authorization"
    db.commit()
    return RedirectResponse(url=session.url, status_code=303)


# ========= (D) Webhook: تثبيت نتائج الـ Checkout =========
@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    يستقبل أحداث Stripe:
    - checkout.session.completed → نقرأ الـ PaymentIntent ونحدِّث الحجز.
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    try:
        event = stripe.Webhook.construct_event(payload, sig, endpoint_secret)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        intent_id = session.get("payment_intent")
        pi = stripe.PaymentIntent.retrieve(intent_id) if intent_id else None
        md = (pi.metadata or {}) if pi else {}
        kind = md.get("kind")
        booking_id = int(md.get("booking_id") or 0)

        bk = db.get(Booking, booking_id) if booking_id else None
        if not bk:
            return JSONResponse({"ok": True})

        if kind == "rent":
            # تم تفويض مبلغ الإيجار
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
            # تم تفويض الديبو (hold)
            bk.deposit_hold_intent_id = pi.id
            bk.deposit_status = "held"
            db.commit()
            push_notification(db, bk.owner_id, "تم حجز الديبو",
                              f"حجز #{bk.id}: الديبو محجوز.",
                              f"/bookings/flow/{bk.id}", "deposit")
            push_notification(db, bk.renter_id, "تم حجز الديبو",
                              f"حجز #{bk.id}: الديبو الآن محجوز.",
                              f"/bookings/flow/{bk.id}", "deposit")

    return JSONResponse({"ok": True})


# ========= (E) التقاط مبلغ الإيجار يدويًا (اختياري زر منفصل) =========
@router.post("/api/stripe/capture-rent/{booking_id}")
def capture_rent(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    يلتقط مبلغ الإيجار المؤجَّل (authorized) ويرسله لحساب المالك (Destination).
    مفيد إذا أردت زرًا منفصلًا. في التدفق الكامل عادةً تربطه بزر "تم الاستلام".
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not bk.online_payment_intent_id:
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


# ========= (F) قرار الديبو (Admin أو Deposit Manager) =========
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
      - refund_all        : إلغاء التفويض بالكامل للديبو.
      - withhold_all      : اقتطاع كل الديبو لصالح المالك.
      - withhold_partial  : اقتطاع جزء من الديبو.
    يسمح بتنفيذ القرار لمن لديه صلاحية: Admin أو Deposit Manager.
    """
    require_auth(user)

    # --- (NEW) السماح للأدمِن أو لمتحكّم الوديعة فقط ---
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Deposit decision requires Admin or Deposit Manager")

    bk = require_booking(db, booking_id)
    pi_id = bk.deposit_hold_intent_id
    if not pi_id:
        return flow_redirect(bk.id)

    dep = max(0, bk.deposit_amount or bk.hold_deposit_amount or 0)
    try:
        if action == "refund_all":
            stripe.PaymentIntent.cancel(pi_id)  # يلغي التفويض بالكامل
            bk.deposit_status = "refunded"

        elif action == "withhold_all":
            stripe.PaymentIntent.capture(pi_id, amount_to_capture=dep * 100)
            bk.deposit_status = "claimed"
            bk.deposit_charged_amount = dep

        elif action == "withhold_partial":
            amt = max(0, int(partial_amount or 0))
            if amt <= 0 or amt >= dep:
                raise HTTPException(status_code=400, detail="Invalid partial amount")
            stripe.PaymentIntent.capture(pi_id, amount_to_capture=amt * 100)
            bk.deposit_status = "partially_withheld"
            bk.deposit_charged_amount = amt

        else:
            raise HTTPException(status_code=400, detail="Unknown action")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe deposit op failed: {e}")

    db.commit()
    return flow_redirect(bk.id)
