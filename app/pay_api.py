#pay_api.py
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional, Literal, Callable
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
import requests
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET")
PAYPAL_BASE = "https://api-m.sandbox.paypal.com"  # sandbox الآن


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
# ===== Real Email Service (same as admin.py) =====
try:
    from .email_service import send_email as real_send_email
except Exception:
    real_send_email = None

def send_payment_email(to_email: str, subject: str, html: str, text: str):
    try:
        if real_send_email:
            return real_send_email(
                to=to_email,
                subject=subject,
                html_body=html,
                text_body=text
            )
    except:
        pass
    return False


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


def paypal_token():
    r = requests.post(
        f"{PAYPAL_BASE}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        data={"grant_type": "client_credentials"},
    )
    r.raise_for_status()
    return r.json()["access_token"]


@router.post("/api/paypal/checkout/{booking_id}")
def paypal_checkout(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)

    if user.id != bk.renter_id:
        raise HTTPException(status_code=403)

    token = paypal_token()

    amount = bk.total_amount or bk.rent_amount
    currency = (bk.currency_display or "USD").upper()

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": str(bk.id),
            "amount": {
                "currency_code": currency,
                "value": f"{amount:.2f}"
            }
        }],
        "application_context": {
            "return_url": f"{BASE_URL}/paypal/success?bid={bk.id}",
            "cancel_url": f"{BASE_URL}/paypal/cancel?bid={bk.id}"
        }
    }

    r = requests.post(
        f"{PAYPAL_BASE}/v2/checkout/orders",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    r.raise_for_status()
    data = r.json()

    bk.payment_provider = "paypal"
    bk.paypal_order_id = data["id"]
    db.commit()

    approve = next(l["href"] for l in data["links"] if l["rel"] == "approve")
    return RedirectResponse(approve, status_code=303)
