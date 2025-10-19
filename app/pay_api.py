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

# ===== إضافة: خدمة بريد موحّدة (HTML) + سقوط نصي =====
BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
try:
    # ستتوفر لاحقًا في app/emailer.py
    from .emailer import send_email as _templated_send_email  # (to, subject, html_body, text_body=None, ...)
except Exception:
    _templated_send_email = None

def _strip_html(html: str) -> str:
    try:
        import re
        txt = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
        txt = re.sub(r"</p\s*>", "\n\n", txt, flags=re.I)
        txt = re.sub(r"<[^>]+>", "", txt)
        return txt.strip()
    except Exception:
        return html

def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """يحاول emailer.send_email ثم يسقط لإرسال نصي عبر SMTP test_email.py لديك (إن مُعد)؛
       هنا نكتفي بالمحاولة عبر emailer فقط (fallback آمن بصمت)."""
    try:
        if _templated_send_email:
            ok = bool(_templated_send_email(to_email, subject, html_body, text_body=text_body))
            if ok:
                return True
    except Exception:
        pass
    # سقوط صامت (بدون SMTP خام هنا كي لا نكرر الكود) — لن يكسر التدفق.
    return False

# ================= Stripe Config =================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")  # sk_test_... / sk_live_...

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

# ====== Helpers إضافية للفواتير ======
def _fmt_money_cents(amount_cents: int, currency: str | None = None) -> str:
    try:
        unit = (currency or CURRENCY or "cad").upper()
        return f"{amount_cents/100:,.2f} {unit}"
    except Exception:
        return str(amount_cents)

def _latest_charge_id(pi: dict | stripe.PaymentIntent | None) -> str | None:
    try:
        if not pi:
            return None
        ch = getattr(pi, "latest_charge", None) or (getattr(pi, "charges", None) or {}).get("data", [{}])[0].get("id")
        return ch
    except Exception:
        return None

def _user_email(db: Session, user_id: int) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return (u.email or None) if u else None

def _compose_invoice_html(
    bk: Booking,
    renter: User | None,
    item: Item | None,
    amount_txt: str,
    currency: str,
    pi_id: str | None,
    charge_id: str | None,
    when: datetime,
) -> tuple[str, str]:
    """يرجع (html, text)."""
    item_title = getattr(item, "title", "") or "Item"
    renter_name = (getattr(renter, "first_name", "") or "").strip() or "Customer"
    order_dt = when.strftime("%Y-%m-%d %H:%M UTC")
    booking_url = f"{SITE_URL}/bookings/flow/{bk.id}"
    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;line-height:1.6">
      <h3>إيصال الدفع — حجز #{bk.id}</h3>
      <p>مرحبًا {renter_name},</p>
      <p>تم تسجيل دفعتك بنجاح.</p>
      <table style="border-collapse:collapse;min-width:320px">
        <tr><td style="padding:4px 8px"><b>العنصر</b></td><td style="padding:4px 8px">{item_title}</td></tr>
        <tr><td style="padding:4px 8px"><b>رقم الحجز</b></td><td style="padding:4px 8px">#{bk.id}</td></tr>
        <tr><td style="padding:4px 8px"><b>التاريخ</b></td><td style="padding:4px 8px">{order_dt}</td></tr>
        <tr><td style="padding:4px 8px"><b>المبلغ</b></td><td style="padding:4px 8px">{amount_txt}</td></tr>
        <tr><td style="padding:4px 8px"><b>العملة</b></td><td style="padding:4px 8px">{currency.upper()}</td></tr>
        <tr><td style="padding:4px 8px"><b>PaymentIntent</b></td><td style="padding:4px 8px">{pi_id or "-"}</td></tr>
        <tr><td style="padding:4px 8px"><b>Charge</b></td><td style="padding:4px 8px">{charge_id or "-"}</td></tr>
      </table>
      <p style="margin-top:12px">
        يمكنك متابعة الحجز من هنا: <a href="{booking_url}">{booking_url}</a>
      </p>
      <p style="color:#888;font-size:12px">هذه الرسالة للتأكيد ولا تتطلب أي إجراء.</p>
    </div>
    """
    text = (
        f"إيصال الدفع — حجز #{bk.id}\n\n"
        f"مرحبًا {renter_name},\n"
        f"تم تسجيل دفعتك بنجاح.\n\n"
        f"العنصر: {item_title}\n"
        f"رقم الحجز: #{bk.id}\n"
        f"التاريخ: {order_dt}\n"
        f"المبلغ: {amount_txt}\n"
        f"العملة: {currency.upper()}\n"
        f"PaymentIntent: {pi_id or '-'}\n"
        f"Charge: {charge_id or '-'}\n\n"
        f"رابط الحجز: {booking_url}\n"
    )
    return html, text


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
    - بعد نجاح الـ Checkout، webhook يحدّث الحجز.
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
        raise HTTPException(status_code=404, detail="Item not found")

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
    """منطق المعالجة الفعلي للويبهوك (نستدعيه من المسار أدناه)."""
    intent_id = session_obj.get("payment_intent")
    pi = stripe.PaymentIntent.retrieve(intent_id) if intent_id else None
    md = (pi.metadata or {}) if pi else {}
    kind = md.get("kind")
    booking_id = int(md.get("booking_id") or 0)

    bk = db.get(Booking, booking_id) if booking_id else None
    if not bk:
        return

    # ====== تجهيز بيانات الفاتورة من الـ Session/PI ======
    amount_total_cents = int(session_obj.get("amount_total") or 0)  # إجمالي جلسة Checkout
    currency = (session_obj.get("currency") or CURRENCY or "cad").lower()
    charge_id = _latest_charge_id(pi)
    when = datetime.utcnow()

    # سنحتاج بيانات العنصر والمستأجر لبناء الفاتورة
    renter = db.get(User, bk.renter_id) if bk.renter_id else None
    item = db.get(Item, bk.item_id) if bk.item_id else None

    if kind == "rent":
        # مفوّض الإيجار — لا نغيّر الحجز إلى paid إلا إذا كانت الوديعة محجوزة مسبقًا
        bk.online_payment_intent_id = pi.id
        bk.online_status = "authorized"

        # إن كانت الوديعة محجوزة بالفعل، يصبح الحجز جاهزًا للاستلام
        if (bk.deposit_status or "").lower() == "held":
            bk.status = "paid"
            bk.timeline_paid_at = datetime.utcnow()
            db.commit()
            push_notification(db, bk.owner_id, "تم تفويض دفعة الإيجار",
                              f"حجز #{bk.id}: التفويض جاهز. سلّم الغرض عند الموعد.",
                              f"/bookings/flow/{bk.id}", "booking")
            push_notification(db, bk.renter_id, "تم تفويض الإيجار + الوديعة محجوزة",
                              f"حجز #{bk.id}. يمكنك استلام الغرض الآن.",
                              f"/bookings/flow/{bk.id}", "booking")
        else:
            # فقط إشعار بأن الإيجار تفوَّض ويجب حجز الوديعة لإكمال العملية
            db.commit()
            push_notification(db, bk.owner_id, "تم تفويض دفعة الإيجار",
                              f"حجز #{bk.id}: انتظر حجز الوديعة قبل التسليم.",
                              f"/bookings/flow/{bk.id}", "booking")
            push_notification(db, bk.renter_id, "تم تفويض الإيجار",
                              f"حجز #{bk.id}: رجاءً أكمل حجز الوديعة للانتقال للاستلام.",
                              f"/bookings/flow/{bk.id}", "booking")

        # إيصال الإيجار اختياري — نبقيه كما هو
        try:
            renter_email = _user_email(db, bk.renter_id)
            amt_cents = amount_total_cents if amount_total_cents > 0 else int(max(0, (bk.total_amount or 0)) * 100)
            amount_txt = _fmt_money_cents(amt_cents, currency)
            if renter_email:
                html, text = _compose_invoice_html(
                    bk=bk,
                    renter=renter,
                    item=item,
                    amount_txt=amount_txt,
                    currency=currency,
                    pi_id=pi.id if pi else None,
                    charge_id=charge_id,
                    when=when,
                )
                send_email(renter_email, f"🧾 إيصال الدفع — حجز #{bk.id}", html, text_body=text)
        except Exception:
            pass

    elif kind == "deposit":
        _set_deposit_pi_id(bk, pi.id)
        bk.deposit_status = "held"

        # إذا كان الإيجار مفوضًا بالفعل، نُتم العملية ونحوّل إلى paid
        if (bk.online_status or "").lower() == "authorized":
            bk.status = "paid"
            bk.timeline_paid_at = datetime.utcnow()

            # إرسال الإيصال الكامل (الإيجار + الوديعة) عند اكتمال الاثنين
            try:
                renter_email = _user_email(db, bk.renter_id)
                amt_cents = (
                    int(max(0, (bk.total_amount or 0)) * 100) +
                    int(max(0, (bk.deposit_amount or getattr(bk, "hold_deposit_amount", 0) or 0)) * 100)
                )
                amount_txt = _fmt_money_cents(amt_cents, currency)
                if renter_email:
                    html, text = _compose_invoice_html(
                        bk=bk,
                        renter=renter,
                        item=item,
                        amount_txt=amount_txt,
                        currency=currency,
                        pi_id=pi.id if pi else None,
                        charge_id=charge_id,
                        when=when,
                    )
                    send_email(renter_email, f"🧾 إيصال الدفع — حجز #{bk.id}", html, text_body=text)
            except Exception:
                pass

            db.commit()
            push_notification(db, bk.owner_id, "اكتمل الدفع",
                              f"حجز #{bk.id}: الإيجار مفوَّض والوديعة محجوزة.",
                              f"/bookings/flow/{bk.id}", "booking")
            push_notification(db, bk.renter_id, "جاهز للاستلام",
                              f"حجز #{bk.id}: يمكنك استلام الغرض الآن.",
                              f"/bookings/flow/{bk.id}", "booking")
        else:
            db.commit()
            push_notification(db, bk.owner_id, "تم حجز الديبو",
                              f"حجز #{bk.id}: الديبو محجوز. بانتظار تفويض الإيجار.",
                              f"/bookings/flow/{bk.id}", "deposit")
            push_notification(db, bk.renter_id, "تم حجز الديبو",
                              f"حجز #{bk.id}: أكمل دفع الإيجار للانتقال للاستلام.",
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

        # إيصال الإجمالي
        try:
            renter_email = _user_email(db, bk.renter_id)
            amt_cents = amount_total_cents if amount_total_cents > 0 else (
                int(max(0, (bk.total_amount or 0)) * 100) +
                int(max(0, (bk.deposit_amount or getattr(bk, "hold_deposit_amount", 0) or 0)) * 100)
            )
            amount_txt = _fmt_money_cents(amt_cents, currency)
            if renter_email:
                html, text = _compose_invoice_html(
                    bk=bk,
                    renter=renter,
                    item=item,
                    amount_txt=amount_txt,
                    currency=currency,
                    pi_id=pi.id if pi else None,
                    charge_id=charge_id,
                    when=when,
                )
                send_email(renter_email, f"🧾 إيصال الدفع — حجز #{bk.id}", html, text_body=text)
        except Exception:
            pass


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

        return JSONResponse({"ok": True})
    return _handler

# ⚠️ مهم: نستخدم مسار واحد هنا لتفادي التعارض مع app/webhooks.py
router.post("/webhooks/stripe")(_webhook_handler_factory())


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
        return flow_redirect(bk.id)

    dep = int(max(0, bk.deposit_amount or getattr(bk, "hold_deposit_amount", 0) or 0))
    try:
        if action == "refund_all":
            stripe.PaymentIntent.cancel(pi_id)
            bk.deposit_status = "refunded"
            bk.deposit_charged_amount = 0

        elif action == "withhold_all":
            stripe.PaymentIntent.capture(pi_id, amount_to_capture=dep * 100)
            bk.deposit_status = "claimed"
            bk.deposit_charged_amount = dep

        elif action == "withhold_partial":
            amt = int(max(0, partial_amount or 0))
            if amt <= 0 or amt >= dep:
                raise HTTPException(status_code=400, detail="Invalid partial amount")
            stripe.PaymentIntent.capture(pi_id, amount_to_capture=amt * 100)
            bk.deposit_status = "partially_withheld"
            prev = int(getattr(bk, "deposit_charged_amount", 0) or 0)
            bk.deposit_charged_amount = prev + amt

        else:
            raise HTTPException(status_code=400, detail="Unknown action")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe deposit op failed: {e}")

    db.commit()

    notify_admins(db, "تم تنفيذ قرار وديعة", f"حجز #{bk.id}: {action}.", f"/bookings/flow/{bk.id}")
    push_notification(db, bk.owner_id, "قرار الوديعة",
                      f"تم تنفيذ القرار: {action}.", f"/bookings/flow/{bk.id}", "deposit")
    push_notification(db, bk.renter_id, "قرار الوديعة",
                      f"تم تنفيذ القرار: {action}.", f"/bookings/flow/{bk.id}", "deposit")

    return flow_redirect(bk.id)


# ============ (G) (اختياري) API لـ Elements (PaymentIntent مباشر) ============
@router.post("/api/checkout/{booking_id}/intent")
def create_payment_intent_elements(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    بديل اختياري لو أردت استخدام Stripe Elements بدل Checkout.
    ينشئ PaymentIntent بمبلغ الإيجار (manual capture) + metadata فقط.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay")
    if bk.status not in ("accepted", "requested"):
        raise HTTPException(status_code=400, detail="Booking is not payable now")

    owner = db.get(User, bk.owner_id)
    if not owner or not getattr(owner, "stripe_account_id", None):
        raise HTTPException(status_code=400, detail="Owner is not onboarded to Stripe")

    rent_cents = int(max(0, (bk.total_amount or 0)) * 100)
    if rent_cents <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    app_fee_cents = (rent_cents * PLATFORM_FEE_PCT) // 100 if PLATFORM_FEE_PCT > 0 else 0

    kwargs = dict(
        amount=rent_cents,
        currency=CURRENCY,
        capture_method="manual",
        metadata={"kind": "rent", "booking_id": str(bk.id)},
        transfer_data={"destination": owner.stripe_account_id},
        automatic_payment_methods={"enabled": True},
    )
    if app_fee_cents > 0:
        kwargs["application_fee_amount"] = app_fee_cents

    try:
        pi = stripe.PaymentIntent.create(**kwargs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")

    # نحفظ حالة انتظار
    bk.payment_method = "online"
    bk.online_status = "pending_authorization"
    bk.online_payment_intent_id = pi.id
    db.commit()

    return {"clientSecret": pi.client_secret}


# >>> NEW: Endpoint حالة بسيط لتفعيل/تعطيل الأزرار في الواجهة
@router.get("/api/stripe/checkout/state/{booking_id}")
def checkout_state(booking_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    """يرجّع إذا كان الإيجار مُفوَّضًا والوديعة محجوزة؛ مفيد لتغيير نص الأزرار في الواجهة."""
    require_auth(user)
    bk = require_booking(db, booking_id)
    return {
        "rent_authorized": (bk.online_status == "authorized"),
        "rent_captured": (bk.online_status == "captured"),
        "deposit_held": (bk.deposit_status == "held"),
        "ready_for_pickup": (bk.online_status == "authorized" and bk.deposit_status == "held"),
    }