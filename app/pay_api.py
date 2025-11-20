#pay_api.py
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional, Literal, Callable
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING

import stripe
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, Item, User
from .notifications_api import push_notification, notify_admins
from .utili_tax import compute_order_taxes
from .items import _display_currency, fx_convert_smart

# ===== Email helper =====
BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
try:
    from .emailer import send_email as _templated_send_email
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
    try:
        if _templated_send_email:
            ok = bool(_templated_send_email(to_email, subject, html_body, text_body=text_body))
            if ok:
                return True
    except Exception:
        pass
    return False

# ================= Stripe Config =================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
SITE_URL = (os.getenv("SITE_URL", "http://localhost:8000") or "").rstrip("/")
CURRENCY = (os.getenv("CURRENCY", "cad") or "cad").lower()

try:
    PLATFORM_FEE_PCT = float(os.getenv("PLATFORM_FEE_PCT", "1"))
except Exception:
    PLATFORM_FEE_PCT = 1.0

try:
    STRIPE_PROCESSING_PCT = float(os.getenv("STRIPE_PROCESSING_PCT", "0.029"))
except Exception:
    STRIPE_PROCESSING_PCT = 0.029
try:
    STRIPE_PROCESSING_FIXED_CENTS = int(os.getenv("STRIPE_PROCESSING_FIXED_CENTS", "30"))
except Exception:
    STRIPE_PROCESSING_FIXED_CENTS = 30

if not stripe.api_key:
    raise RuntimeError("STRIPE_SECRET_KEY is missing in environment")

router = APIRouter(tags=["payments"])

# ================= Geo QS helpers =================
def _loc_qs_for_user(u: Optional[User]) -> str:
    if not u:
        return ""
    country = (getattr(u, "country", None) or getattr(u, "geo_country", None) or "").strip().upper()
    sub     = (getattr(u, "region", None)  or getattr(u, "state", None)
               or getattr(u, "geo_region", None) or "").strip().upper()
    if country and sub:
        return f"?loc={country}-{sub}"
    if country:
        if country == "CA":
            return f"?loc=CA-QC"
        return f"?loc={country}"
    return ""

def _loc_qs_for_booking(bk: Optional[Booking]) -> str:
    if not bk:
        return ""
    c = (getattr(bk, "loc_country", "") or "").strip().upper()
    s = (getattr(bk, "loc_sub", "") or "").strip().upper()
    if c and s:
        return f"?loc={c}-{s}"
    if c:
        if c == "CA":
            return f"?loc=CA-QC"
        return f"?loc={c}"
    return ""

def _best_loc_qs(bk: Optional[Booking], renter: Optional[User]) -> str:
    return _loc_qs_for_booking(bk) or _loc_qs_for_user(renter) or ""

def _append_qs(url: str, qs: str) -> str:
    if not qs:
        return url
    if "?" in url:
        base, tail = url.split("?", 1)
        if qs.startswith("?"):
            qs = qs[1:]
        return f"{base}?{qs}&{tail}" if tail else f"{base}?{qs}"
    return f"{url}{qs}"

def _geo_for_booking_and_user(bk: Booking, renter: Optional[User]) -> dict:
    geo = {}
    c = (getattr(bk, "loc_country", None) or "").strip().upper()
    s = (getattr(bk, "loc_sub", None) or "").strip().upper()
    if c:
        geo["country"] = c
    if s:
        geo["sub"] = s
    if not geo.get("country") and renter:
        cc = (getattr(renter, "country", None) or getattr(renter, "geo_country", None) or "").strip().upper()
        if cc: geo["country"] = cc
    if not geo.get("sub") and renter:
        ss = (getattr(renter, "region", None) or getattr(renter, "state", None)
              or getattr(renter, "geo_region", None) or "").strip().upper()
        if ss: geo["sub"] = ss
    return geo
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

def flow_redirect(bid: int, db: Session = None) -> RedirectResponse:
    if db:
        bk = db.get(Booking, bid)
        renter = db.get(User, bk.renter_id) if (bk and bk.renter_id) else None
        qs = _best_loc_qs(bk, renter)
    else:
        qs = ""
    return RedirectResponse(url=_append_qs(f"/bookings/flow/{bid}", qs), status_code=303)

def can_manage_deposits(u: Optional[User]) -> bool:
    if not u:
        return False
    if (getattr(u, "role", "") or "").lower() == "admin":
        return True
    return bool(getattr(u, "is_deposit_manager", False))

def _get_deposit_pi_id(bk: Booking) -> Optional[str]:
    return getattr(bk, "deposit_hold_intent_id", None) or getattr(bk, "deposit_hold_id", None)

def _set_deposit_pi_id(bk: Booking, pi_id: Optional[str]) -> None:
    try:
        setattr(bk, "deposit_hold_intent_id", pi_id)
    except Exception:
        pass
    try:
        setattr(bk, "deposit_hold_id", pi_id)
    except Exception:
        pass

# ===== Invoice helpers =====
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
    return u.email if u else None

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

    item_title = getattr(item, "title", "") or "Item"
    renter_name = (getattr(renter, "first_name", "") or "").strip() or "Customer"
    order_dt = when.strftime("%Y-%m-%d %H:%M UTC")
    booking_url = f"{SITE_URL}/bookings/flow/{bk.id}"

    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;line-height:1.6">
      <h3>Payment Receipt — Booking #{bk.id}</h3>
      <p>Hello {renter_name},</p>
      <p>Your payment has been recorded successfully.</p>
      <table style="border-collapse:collapse;min-width:320px">
        <tr><td style="padding:4px 8px"><b>Item</b></td><td style="padding:4px 8px">{item_title}</td></tr>
        <tr><td style="padding:4px 8px"><b>Booking Number</b></td><td style="padding:4px 8px">#{bk.id}</td></tr>
        <tr><td style="padding:4px 8px"><b>Date</b></td><td style="padding:4px 8px">{order_dt}</td></tr>
        <tr><td style="padding:4px 8px"><b>Amount</b></td><td style="padding:4px 8px">{amount_txt}</td></tr>
        <tr><td style="padding:4px 8px"><b>Currency</b></td><td style="padding:4px 8px">{currency.upper()}</td></tr>
        <tr><td style="padding:4px 8px"><b>PaymentIntent</b></td><td style="padding:4px 8px">{pi_id or "-"}</td></tr>
        <tr><td style="padding:4px 8px"><b>Charge</b></td><td style="padding:4px 8px">{charge_id or "-"}</td></tr>
      </table>
      <p style="margin-top:12px">You can follow the booking here:
        <a href="{booking_url}">{booking_url}</a>
      </p>
      <p style="color:#888;font-size:12px">This message is for confirmation only.</p>
    </div>
    """

    text = (
        f"Payment Receipt — Booking #{bk.id}\n\n"
        f"Hello {renter_name},\n"
        f"Your payment has been recorded successfully.\n\n"
        f"Item: {item_title}\n"
        f"Booking: #{bk.id}\n"
        f"Date: {order_dt}\n"
        f"Amount: {amount_txt}\n"
        f"Currency: {currency.upper()}\n"
        f"PaymentIntent: {pi_id or '-'}\n"
        f"Charge: {charge_id or '-'}\n\n"
        f"Booking link: {booking_url}\n"
    )
    return html, text

# ===== Processing fee helper =====
def _processing_fee_cents_for_rent(rent_cents: int) -> int:
    base = Decimal(rent_cents)
    pct  = Decimal(str(STRIPE_PROCESSING_PCT))
    fx   = Decimal(STRIPE_PROCESSING_FIXED_CENTS)
    fee  = (base * pct) + fx
    return int(fee.to_integral_value(rounding=ROUND_CEILING))
# Checkout: Rent + Deposit together

@router.post("/api/stripe/checkout/all/{booking_id}")
def start_checkout_all(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    request: Request = None,     # ← نحتاج request من أجل _display_currency
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay")

    if bk.status not in ("accepted", "requested"):
        return flow_redirect(bk.id, db)

    # ------------------------------------------------
    # 1) Load item + owner
    # ------------------------------------------------
    item = db.get(Item, bk.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    owner = db.get(User, bk.owner_id)
    if not owner or not getattr(owner, "stripe_account_id", None):
        raise HTTPException(status_code=400, detail="Owner not onboarded")

    # ------------------------------------------------
    # 2) Display currency (REAL) ← نفس items_detail
    # ------------------------------------------------
    display_currency = _display_currency(request).lower()

    # ------------------------------------------------
    # 3) Native currency (posting)
    # ------------------------------------------------
    native_currency = (bk.currency_native or item.currency or "cad").lower()

    # ------------------------------------------------
    # 4) Base rent native
    # ------------------------------------------------
    native_amount = float(
        (bk.total_amount or 0)
        or (bk.rent_amount or 0)
        or (getattr(item, "price_per_day", None) or getattr(item, "price", 0))
    )

    if native_amount <= 0:
        return flow_redirect(bk.id, db)

    # ------------------------------------------------
    # 5) Convert native → display
    # ------------------------------------------------
    if native_currency == display_currency:
        display_amount = native_amount
        fx_rate = 1.0
    else:
        display_amount = fx_convert_smart(
            db,
            native_amount,
            native_currency,
            display_currency
        )
        if not display_amount:
            display_amount = native_amount
            fx_rate = 1.0
        else:
            fx_rate = display_amount / native_amount

    # ------------------------------------------------
    # 6) Save snapshot
    # ------------------------------------------------
    bk.currency_native = native_currency.upper()
    bk.currency_display = display_currency.upper()
    bk.currency_paid = display_currency
    bk.amount_display = display_amount
    bk.rent_amount = native_amount
    bk.fx_rate_native_to_paid = fx_rate
    db.commit()

    # ------------------------------------------------
    # 7) Convert to cents for Stripe
    # ------------------------------------------------
    rent_cents = int(round(display_amount * 100))
    dep = float(bk.deposit_amount or getattr(bk, "hold_deposit_amount", 0) or 0)
    dep_cents = int(round(dep * 100))

    if rent_cents <= 0 and dep_cents <= 0:
        return flow_redirect(bk.id, db)

    platform_fee_cents = int(round(rent_cents * (PLATFORM_FEE_PCT / 100.0)))
    transfer_amount = max(0, rent_cents - platform_fee_cents)
    processing_cents = _processing_fee_cents_for_rent(rent_cents)

    # ------------------------------------------------
    # 8) Success & cancel URL
    # ------------------------------------------------
    renter = db.get(User, bk.renter_id)
    qs = _best_loc_qs(bk, renter)
    success_url = _append_qs(f"{SITE_URL}/bookings/flow/{bk.id}", qs)
    cancel_url  = _append_qs(f"{SITE_URL}/bookings/flow/{bk.id}", qs)

    # ------------------------------------------------
    # 9) Taxes in display currency
    # ------------------------------------------------
    geo = _geo_for_booking_and_user(bk, renter)
    subtotal_before_tax_cents = rent_cents + processing_cents + dep_cents

    line_items = [
        {
            "quantity": 1,
            "price_data": {
                "currency": display_currency,
                "product_data": {"name": f"Rent for '{item.title}' (#{bk.id})"},
                "unit_amount": rent_cents,
                "tax_behavior": "exclusive",
            },
        },
        {
            "quantity": 1,
            "price_data": {
                "currency": display_currency,
                "product_data": {"name": "Processing fee"},
                "unit_amount": processing_cents,
                "tax_behavior": "exclusive",
            },
        },
    ]

    if dep_cents > 0:
        line_items.append({
            "quantity": 1,
            "price_data": {
                "currency": display_currency,
                "product_data": {"name": f"Deposit for '{item.title}' (#{bk.id})"},
                "unit_amount": dep_cents,
                "tax_behavior": "exclusive",
            },
        })

    tax_lines = []
    try:
        if geo.get("country"):
            _calc = compute_order_taxes(subtotal_before_tax_cents / 100.0, geo)
            for t in _calc.get("lines", []):
                cents = int(round(float(t["amount"]) * 100))
                if cents > 0:
                    tax_lines.append({
                        "quantity": 1,
                        "price_data": {
                            "currency": display_currency,
                            "product_data": {
                                "name": f"{t['name']} {round(float(t['rate'])*100,3)}%"
                            },
                            "unit_amount": cents,
                        },
                    })
    except:
        pass

    automatic_tax_payload = {"enabled": False} if tax_lines else {"enabled": True}
    line_items.extend(tax_lines)

    # ------------------------------------------------
    # 10) PaymentIntent metadata
    # ------------------------------------------------
    pi_data = {
        "capture_method": "manual",
        "metadata": {
            "kind": "all",
            "booking_id": str(bk.id),
            "currency_paid": display_currency,
            "currency_display": display_currency,
            "currency_native": native_currency,
            "fx_rate": fx_rate,
        },
        "transfer_data": {
            "destination": owner.stripe_account_id,
            "amount": transfer_amount,
        },
    }

    # ------------------------------------------------
    # 11) Create Stripe checkout (FIXED)
    # ------------------------------------------------
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            currency=display_currency,          # ← ← ★ المفتاح ★
            payment_intent_data=pi_data,
            automatic_tax=automatic_tax_payload,
            tax_id_collection={"enabled": True},
            billing_address_collection="required",
            customer_creation="always",
            line_items=line_items,
            success_url=f"{success_url}&all_ok=1&sid={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{cancel_url}&cancel=1",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")

    # ------------------------------------------------
    # 12) Save status
    # ------------------------------------------------
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
    require_auth(user)

    # Create express account if missing
    if not getattr(user, "stripe_account_id", None):
        try:
            account = stripe.Account.create(type="express")
            user.stripe_account_id = account.id
            db.commit()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Stripe create account failed: {e}")

    # Create onboarding link
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

@router.post("/api/stripe/checkout/rent/{booking_id}")
def start_checkout_rent(
    booking_id: int,
    request: Request,  
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay")

    if bk.status not in ("accepted", "requested"):
        return flow_redirect(bk.id, db)

    item = db.get(Item, bk.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    owner = db.get(User, bk.owner_id)
    if not owner or not getattr(owner, "stripe_account_id", None):
        raise HTTPException(status_code=400, detail="Owner is not onboarded to Stripe")
    # نأخذ عملة العرض الحقيقية التي يستعملها الموقع الآن (نفس items_detail و home)
    disp_cur = _display_currency(request).lower()

    # عملة المنشور / العملة الأصلية
    native_currency = (bk.currency_native or item.currency or CURRENCY or "cad").lower()

    # المبلغ الأصلي (إيجار كامل بالعملة الأصلية)
    native_amount = float(
        (bk.total_amount or 0)
        or (bk.rent_amount or 0)
        or (getattr(item, "price_per_day", None) or getattr(item, "price", 0) or 0)
    )

    if native_amount <= 0:
        return flow_redirect(bk.id, db)

    # عملة العرض (التي يرى بها المستخدم السعر في الموقع) = من helper الموحد
    display_currency = disp_cur

    # تحويل من native → display
    if native_currency == display_currency:
        display_amount = native_amount
        fx_rate = 1.0
    else:
        display_amount = fx_convert_smart(
            db,
            native_amount,
            native_currency,
            display_currency
        )
        if not display_amount:
            display_amount = native_amount
            fx_rate = 1.0
        else:
            fx_rate = display_amount / native_amount

    # =======================================================
    # 2) تخزين Snapshot صحيح داخل booking
    #    حتى يصبح Stripe = نفس أرقام صفحة Sevor
    # =======================================================
    bk.currency_native = native_currency.upper()
    bk.currency_display = display_currency.upper()
    bk.currency_paid = display_currency          # Stripe سيدفع بهذه العملة
    bk.rent_amount = native_amount               # الإيجار بالعملة الأصلية
    bk.amount_display = display_amount           # الإيجار بعملة العرض
    bk.fx_rate_native_to_paid = fx_rate          # FX المستخدم فعليًا
    db.commit()

    # =======================================================
    # 3) حول السعر المعروض إلى cents (هو الذي سيذهب لـ Stripe)
    # =======================================================
    rent_cents = int(round(display_amount * 100))

    if rent_cents <= 0:
        return flow_redirect(bk.id, db)

    platform_fee_cents = int(round(rent_cents * (PLATFORM_FEE_PCT / 100.0)))
    transfer_amount = max(0, rent_cents - platform_fee_cents)
    processing_cents = _processing_fee_cents_for_rent(rent_cents)

    currency_paid = display_currency

    renter = db.get(User, bk.renter_id) if bk.renter_id else None
    qs = _best_loc_qs(bk, renter)
    success_url = _append_qs(f"{SITE_URL}/bookings/flow/{bk.id}", qs)
    cancel_url  = _append_qs(f"{SITE_URL}/bookings/flow/{bk.id}", qs)

    # =======================================================
    # 4) Taxes (manual or automatic) بنفس عملة الدفع
    # =======================================================
    geo = _geo_for_booking_and_user(bk, renter)
    subtotal_before_tax_cents = rent_cents + processing_cents

    line_items = [
        {
            "quantity": 1,
            "price_data": {
                "currency": currency_paid,
                "product_data": {"name": f"Rent for '{item.title}' (#{bk.id})"},
                "unit_amount": rent_cents,
                "tax_behavior": "exclusive",
            },
        },
        {
            "quantity": 1,
            "price_data": {
                "currency": currency_paid,
                "product_data": {"name": "Processing fee"},
                "unit_amount": processing_cents,
                "tax_behavior": "exclusive",
            },
        },
    ]

    tax_lines = []
    try:
        if geo.get("country"):
            _calc = compute_order_taxes(subtotal_before_tax_cents / 100.0, geo)
            for t in (_calc.get("lines") or []):
                amt_cents = int(round(float(t.get("amount") or 0) * 100))
                if amt_cents > 0:
                    tax_lines.append({
                        "quantity": 1,
                        "price_data": {
                            "currency": currency_paid,
                            "product_data": {
                                "name": f"{t.get('name','Tax')} {round(float(t.get('rate',0))*100,3)}%"
                            },
                            "unit_amount": amt_cents,
                        },
                    })
    except Exception:
        pass

    automatic_tax_payload = {"enabled": False} if tax_lines else {"enabled": True}
    line_items.extend(tax_lines)

    # =======================================================
    # 5) Stripe Session + metadata snapshot
    # =======================================================
    pi_data = {
        "capture_method": "manual",
        "metadata": {
            "kind": "rent",
            "booking_id": str(bk.id),
            "currency_paid": display_currency,
            "currency_display": display_currency,
            "currency_native": native_currency,
            "fx_rate": fx_rate,
        },
        "transfer_data": {
            "destination": owner.stripe_account_id,
            "amount": transfer_amount,
        },
    }

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_intent_data=pi_data,
            automatic_tax=automatic_tax_payload,
            tax_id_collection={"enabled": True},
            billing_address_collection="required",
            customer_creation="always",
            line_items=line_items,
            success_url=f"{success_url}&rent_ok=1&sid={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{cancel_url}&cancel=1",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")

    return RedirectResponse(url=session.url, status_code=303)

@router.post("/api/stripe/checkout/deposit/{booking_id}")
def start_checkout_deposit(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)

    bk = require_booking(db, booking_id)
    if user.id != bk.renter_id:
        raise HTTPException(status_code=403, detail="Only renter can pay deposit")

    dep = int(max(0, bk.deposit_amount or getattr(bk, "hold_deposit_amount", 0) or 0))
    if dep <= 0:
        return flow_redirect(bk.id, db)

    # Load item and real posting currency
    item = db.get(Item, bk.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item_currency = (item.currency or "cad").lower()

    # Save deposit snapshot
    bk.deposit_currency = item_currency.upper()
    bk.deposit_amount = dep
    bk.hold_deposit_amount = dep
    db.commit()

    renter = db.get(User, bk.renter_id) if bk.renter_id else None
    qs = _best_loc_qs(bk, renter)

    success_url = _append_qs(f"{SITE_URL}/bookings/flow/{bk.id}", qs)
    cancel_url  = _append_qs(f"{SITE_URL}/bookings/flow/{bk.id}", qs)

    # Stripe Session
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_intent_data={
                "capture_method": "manual",
                "metadata": {
                    "kind": "deposit",
                    "booking_id": str(bk.id),
                    "deposit_currency": item_currency,   # FIXED
                },
            },
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": item_currency,            # FIXED
                        "product_data": {
                            "name": f"Deposit hold for '{item.title}' (#{bk.id})"
                        },
                        "unit_amount": dep * 100,
                        "tax_behavior": "exclusive",
                    },
                }
            ],
            automatic_tax={"enabled": False},
            billing_address_collection="required",
            customer_creation="always",
            success_url=f"{success_url}&deposit_ok=1&sid={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{cancel_url}&cancel=1",
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")

    bk.online_status = bk.online_status or "pending_authorization"
    db.commit()

    return RedirectResponse(url=session.url, status_code=303)


# ============ (D) Webhook: Persist Checkout results ============
def _handle_checkout_completed(session_obj: dict, db: Session) -> None:
    # 1) Identify PaymentIntent
    intent_id = session_obj.get("payment_intent")
    pi = stripe.PaymentIntent.retrieve(intent_id) if intent_id else None

    # 2) Extract metadata correctly
    md = (pi.metadata or {}) if pi else {}
    kind = md.get("kind")
    booking_id = int(md.get("booking_id") or 0)

    # NEW: Correct key for paid currency
    currency_paid_meta = md.get("currency_paid")

    # 3) Load booking
    bk = db.get(Booking, booking_id) if booking_id else None
    if not bk:
        return

    renter = db.get(User, bk.renter_id) if bk.renter_id else None
    item   = db.get(Item, bk.item_id) if bk.item_id else None
    qs = _best_loc_qs(bk, renter)

    # 4) Amount paid (Stripe real amount)
    amount_total_cents = int(session_obj.get("amount_total") or 0)
    bk.amount_paid_cents = amount_total_cents

    # 5) Currency actually paid
    currency = (session_obj.get("currency") or currency_paid_meta or CURRENCY).lower()
    bk.currency_paid = currency

    # 6) Platform fee currency (always CAD)
    bk.platform_fee_currency = "cad"

    # 7) FX snapshot (already stored earlier, but ensure stored)
    try:
        bk.fx_rate_native_to_paid = (
            bk.fx_rate_native_to_paid
            or md.get("fx_rate")
        )
    except Exception:
        pass

    # 8) Taxes snapshot
    try:
        total_details = session_obj.get("total_details") or {}
        tax_cents = int(total_details.get("amount_tax") or 0)
        bk.tax_total = tax_cents
        bk.tax_details_json = total_details
    except Exception:
        pass

    # 9) Charge ID and timestamp
    charge_id = _latest_charge_id(pi)
    when = datetime.utcnow()

    # =====================================================
    # A) Rent only
    # =====================================================
    if kind == "rent":
        bk.online_payment_intent_id = pi.id
        bk.online_status = "authorized"

        if (bk.deposit_status or "").lower() == "held":
            bk.status = "paid"
            bk.timeline_paid_at = datetime.utcnow()
            db.commit()

            push_notification(
                db, bk.owner_id, "Rent payment authorized",
                f"Booking #{bk.id}: Authorization ready.",
                _append_qs(f"/bookings/flow/{bk.id}", qs),
                "booking"
            )
            push_notification(
                db, bk.renter_id, "Rent authorized + deposit held",
                f"Booking #{bk.id}: You can pick up the item now.",
                _append_qs(f"/bookings/flow/{bk.id}", qs),
                "booking"
            )

        else:
            db.commit()
            push_notification(
                db, bk.owner_id, "Rent payment authorized",
                f"Booking #{bk.id}: Waiting for deposit.",
                _append_qs(f"/bookings/flow/{bk.id}", qs),
                "booking"
            )
            push_notification(
                db, bk.renter_id, "Rent authorized",
                f"Booking #{bk.id}: Please complete the deposit.",
                _append_qs(f"/bookings/flow/{bk.id}", qs),
                "booking"
            )

        # Send receipt
        try:
            renter_email = _user_email(db, bk.renter_id)
            if renter_email:
                amount_txt = _fmt_money_cents(amount_total_cents, currency)
                html, text = _compose_invoice_html(
                    bk=bk, renter=renter, item=item,
                    amount_txt=amount_txt, currency=currency,
                    pi_id=pi.id, charge_id=charge_id, when=when,
                )
                send_email(
                    renter_email,
                    f"🧾 Payment Receipt — Booking #{bk.id}",
                    html,
                    text_body=text,
                )
        except Exception:
            pass

    # =====================================================
    # B) Deposit only
    # =====================================================
    elif kind == "deposit":
        _set_deposit_pi_id(bk, pi.id)
        bk.deposit_status = "held"
        bk.deposit_currency = currency.upper()


        if (bk.online_status or "").lower() == "authorized":
            bk.status = "paid"
            bk.timeline_paid_at = datetime.utcnow()
            db.commit()

            push_notification(
                db, bk.owner_id, "Payment completed",
                f"Booking #{bk.id}: Rent authorized + deposit held.",
                _append_qs(f"/bookings/flow/{bk.id}", qs),
                "booking"
            )
            push_notification(
                db, bk.renter_id, "Ready for pickup",
                f"Booking #{bk.id}: You can pick up now.",
                _append_qs(f"/bookings/flow/{bk.id}", qs),
                "booking"
            )
        else:
            db.commit()
            push_notification(
                db, bk.owner_id, "Deposit held",
                f"Booking #{bk.id}: Waiting for rent payment.",
                _append_qs(f"/bookings/flow/{bk.id}", qs),
                "deposit"
            )
            push_notification(
                db, bk.renter_id, "Deposit held",
                f"Booking #{bk.id}: Complete rent payment.",
                _append_qs(f"/bookings/flow/{bk.id}", qs),
                "deposit"
            )

    # =====================================================
    # C) Rent + Deposit together
    # =====================================================
    elif kind == "all":
        bk.online_payment_intent_id = pi.id
        _set_deposit_pi_id(bk, pi.id)

        bk.online_status = "authorized"
        bk.deposit_status = "held"
        bk.status = "paid"
        bk.timeline_paid_at = datetime.utcnow()
        db.commit()

        push_notification(
            db, bk.owner_id, "Full payment completed",
            f"Booking #{bk.id}: Rent paid + deposit held.",
            _append_qs(f"/bookings/flow/{bk.id}", qs),
            "booking"
        )
        push_notification(
            db, bk.renter_id, "Payment successful",
            f"Rent and deposit paid for booking #{bk.id}.",
            _append_qs(f"/bookings/flow/{bk.id}", qs),
            "booking"
        )


    # END IF

# ============================================================
# (E) Capture the rent amount manually
# ============================================================
@router.post("/api/stripe/capture-rent/{booking_id}")
def capture_rent(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)

    bk = require_booking(db, booking_id)
    if not getattr(bk, "online_payment_intent_id", None):
        return flow_redirect(bk.id, db)

    try:
        stripe.PaymentIntent.capture(bk.online_payment_intent_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe capture failed: {e}")

    bk.payment_status = "released"
    bk.online_status = "captured"
    bk.rent_released_at = datetime.utcnow()
    db.commit()

    renter = db.get(User, bk.renter_id) if bk.renter_id else None
    qs = _best_loc_qs(bk, renter)

    push_notification(
        db, bk.owner_id, "Rent amount transferred",
        f"Booking #{bk.id}: Amount transferred to you.",
        _append_qs(f"/bookings/flow/{bk.id}", qs), "booking"
    )

    return flow_redirect(bk.id, db)
# ============ (F) Deposit decision — MULTI-CURRENCY SAFE VERSION ============
@router.post("/api/stripe/deposit/resolve/{booking_id}")
def resolve_deposit(
    booking_id: int,
    action: Literal["refund_all", "withhold_partial", "withhold_all"] = Form(...),
    partial_amount: int = Form(0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    if not can_manage_deposits(user):
        raise HTTPException(status_code=403, detail="Deposit decision requires Admin or Deposit Manager")

    bk = require_booking(db, booking_id)

    # PaymentIntent ID of the hold
    pi_id = _get_deposit_pi_id(bk)
    if not pi_id:
        return flow_redirect(bk.id, db)

    # Load PaymentIntent (we must read currency from it)
    try:
        pi = stripe.PaymentIntent.retrieve(pi_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot load PI: {e}")

    # Real currency of deposit
    deposit_currency = (pi.metadata.get("deposit_currency") or CURRENCY).lower()

    # Deposit amount (in original item currency)
    dep = int(max(0, bk.deposit_amount or getattr(bk, "hold_deposit_amount", 0) or 0))

    # Process actions
    try:
        if action == "refund_all":
            # Cancel the PaymentIntent → releases the unused authorization
            stripe.PaymentIntent.cancel(pi_id)
            bk.deposit_status = "refunded"
            bk.deposit_charged_amount = 0

        elif action == "withhold_all":
            # Capture the full deposit in SAME currency
            stripe.PaymentIntent.capture(
                pi_id,
                amount_to_capture=dep * 100  # capture in original currency
            )
            bk.deposit_status = "claimed"
            bk.deposit_charged_amount = dep

        elif action == "withhold_partial":
            amt = int(max(0, partial_amount or 0))
            if amt <= 0 or amt >= dep:
                raise HTTPException(status_code=400, detail="Invalid partial amount")

            stripe.PaymentIntent.capture(
                pi_id,
                amount_to_capture=amt * 100  # partial amount in original currency
            )
            bk.deposit_status = "partially_withheld"
            prev = int(getattr(bk, "deposit_charged_amount", 0) or 0)
            bk.deposit_charged_amount = prev + amt

        else:
            raise HTTPException(status_code=400, detail="Unknown action")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe deposit op failed: {e}")

    db.commit()

    # Notifications
    renter = db.get(User, bk.renter_id) if bk.renter_id else None
    qs = _best_loc_qs(bk, renter)

    notify_admins(
        db,
        "Deposit decision executed",
        f"Booking #{bk.id}: {action}.",
        _append_qs(f"/bookings/flow/{bk.id}", qs)
    )

    push_notification(
        db, bk.owner_id, "Deposit decision",
        f"Decision executed: {action}.",
        _append_qs(f"/bookings/flow/{bk.id}", qs),
        "deposit"
    )

    push_notification(
        db, bk.renter_id, "Deposit decision",
        f"Decision executed: {action}.",
        _append_qs(f"/bookings/flow/{bk.id}", qs),
        "deposit"
    )

    return flow_redirect(bk.id, db)
