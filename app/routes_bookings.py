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

# ==== Adapter: يستعمل utili_geo و utili_tax الموجودة لديك (بدون جداول محلية) ====
import os
from fastapi import Request

# نحاول أكثر من اسم/دالة حتى نغطي اختلافات المشروع
try:
    from .utili_geo import (
        geo_from_request as _geo_req,
        locate_from_request as _geo_locate,
        locate_from_session as _geo_session,
    )
except Exception:
    _geo_req = _geo_locate = _geo_session = None

try:
    from .utili_tax import (
        compute_order_taxes as _tax_order,   # (subtotal: float, geo: {"country","sub"}) -> dict
        compute_taxes       as _tax_compute, # (subtotal, country='CA', sub='QC') -> dict
        compute_ca_taxes    as _tax_ca,      # (subtotal, sub='QC') -> (lines, total)
    )
except Exception:
    _tax_order = _tax_compute = _tax_ca = None


def _adapter_geo_from_request(request: Request) -> dict:
    """يرجّع {"country": "CA/US/EU/...", "sub": "QC/ON/CA-STATE/..."} مع دعم override بـ ?loc=CA-QC."""
    # 1) override يدوي عبر query: ?loc=CA-QC
    loc_q = request.query_params.get("loc")
    if loc_q:
        p = loc_q.strip().upper().split("-")
        return {"country": p[0], "sub": (p[1] if len(p) > 1 else None)}

    # 2) utili_geo
    for fn in (_geo_req, _geo_locate, _geo_session):
        if callable(fn):
            try:
                g = fn(request)
                if isinstance(g, dict):
                    country = (g.get("country") or g.get("cc") or "").upper() or None
                    sub     = (g.get("sub") or g.get("region") or g.get("prov") or "").upper() or None
                    if country:
                        return {"country": country, "sub": sub}
            except Exception:
                pass

    # 3) سِـيشن (إن كنت تخزّن loc أو geo)
    s = request.session or {}
    if s.get("loc"):
        p = str(s["loc"]).upper().split("-")
        return {"country": p[0], "sub": (p[1] if len(p) > 1 else None)}
    g = s.get("geo") or {}
    if isinstance(g, dict):
        country = (g.get("country") or g.get("cc") or "").upper() or None
        sub     = (g.get("sub") or g.get("region") or g.get("prov") or "").upper() or None
        if country:
            return {"country": country, "sub": sub}

    return {"country": None, "sub": None}


def _adapter_taxes_for_request(request: Request, subtotal: float) -> dict:
    """
    يُوحّد المخرجات إلى شكل واحد يفهمه القالب:
    {
      "mode": "computed" أو "stripe",
      "currency": "CAD",
      "country": "CA" أو None,
      "sub": "QC" أو None,
      "tax_lines": [{"name":"GST","rate":0.05,"amount":1.23}, ...],
      "tax_total": 1.23 أو None,
      "grand_total": subtotal + tax_total (إن وُجد)
    }
    """
    currency = (os.getenv("CURRENCY", "CAD") or "CAD").upper()
    geo = _adapter_geo_from_request(request)
    country = (geo.get("country") or "").upper() or None
    sub     = (geo.get("sub") or "").upper() or None

    # 1) utili_tax: compute_order_taxes(subtotal, {"country","sub"})
    if callable(_tax_order):
        try:
            res = _tax_order(subtotal, {"country": country, "sub": sub}) or {}
            lines = res.get("lines") or res.get("tax_lines") or []
            total = res.get("total") or res.get("tax_total")
            gtot  = res.get("grand_total") or (subtotal + (total or 0.0))
            norm_lines = []
            for t in lines:
                norm_lines.append({
                    "name": t.get("name") or t.get("code") or "TAX",
                    "rate": float(t.get("rate") or 0.0),
                    "amount": float(t.get("amount") or 0.0),
                })
            return {
                "mode": "computed",
                "currency": currency, "country": country, "sub": sub,
                "tax_lines": norm_lines,
                "tax_total": None if total is None else float(total),
                "grand_total": float(gtot),
            }
        except Exception:
            pass

    # 2) utili_tax: compute_taxes(subtotal, country, sub)
    if callable(_tax_compute):
        try:
            res = _tax_compute(subtotal, country=country, sub=sub) or {}
            lines = res.get("lines") or res.get("tax_lines") or []
            total = res.get("total") or res.get("tax_total")
            gtot  = res.get("grand_total") or (subtotal + (total or 0.0))
            norm_lines = []
            for t in lines:
                norm_lines.append({
                    "name": t.get("name") or t.get("code") or "TAX",
                    "rate": float(t.get("rate") or 0.0),
                    "amount": float(t.get("amount") or 0.0),
                })
            return {
                "mode": "computed",
                "currency": currency, "country": country, "sub": sub,
                "tax_lines": norm_lines,
                "tax_total": None if total is None else float(total),
                "grand_total": float(gtot),
            }
        except Exception:
            pass

    # 3) مثال خاص كندا (لو عندك compute_ca_taxes)
    if callable(_tax_ca) and country == "CA":
        try:
            lines, total = _tax_ca(subtotal, sub=sub or "QC")
            norm_lines = []
            for t in (lines or []):
                if isinstance(t, dict):
                    name = t.get("name") or t.get("code") or "TAX"
                    rate = float(t.get("rate") or 0.0)
                    amt  = float(t.get("amount") or 0.0)
                else:
                    name = (t[0] if len(t) > 0 else "TAX")
                    rate = float(t[1] if len(t) > 1 else 0.0)
                    amt  = float(t[2] if len(t) > 2 else round(subtotal * rate, 2))
                norm_lines.append({"name": name, "rate": rate, "amount": amt})
            total = float(total or sum(x["amount"] for x in norm_lines))
            return {
                "mode": "computed",
                "currency": currency, "country": country, "sub": sub,
                "tax_lines": norm_lines,
                "tax_total": total,
                "grand_total": round(subtotal + total, 2),
            }
        except Exception:
            pass

    # 4) لا شيء → خليه لسترايب
    return {
        "mode": "stripe",
        "currency": currency, "country": country, "sub": sub,
        "tax_lines": [],
        "tax_total": None,
        "grand_total": subtotal,
    }


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

# ===== Stripe helpers for rent capture =====
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

# ===== Deposit PI unifier =====
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

# ====== Create a Stripe deposit authorization (manual capture) and store it on the booking ======
def _ensure_deposit_hold(bk: Booking) -> bool:
    """
    Creates a PaymentIntent (manual capture) for the deposit if missing,
    stores the id in both fields (deposit_hold_intent_id and deposit_hold_id),
    and sets deposit_status='held'.
    """
    try:
        import stripe
        sk = os.getenv("STRIPE_SECRET_KEY", "")
        if not sk:
            return False
        stripe.api_key = sk

        # Already exists?
        if _get_deposit_pi_id(bk):
            return True

        amount = int(getattr(bk, "deposit_amount", 0) or 0)
        if amount <= 0:
            return False

        pi = stripe.PaymentIntent.create(
            amount=amount * 100,                 # Stripe wants cents
            currency="cad",                      # CAD as you use
            capture_method="manual",             # Authorization (manual capture)
            description=f"Deposit hold for booking #{bk.id}",
        )

        _set_deposit_pi_id(bk, pi["id"])
        try:
            bk.deposit_status = "held"
        except Exception:
            pass
        return True
    except Exception:
        return False

# ===== Time policy =====
DISPUTE_WINDOW_HOURS = 48   # Dispute window after return
RENTER_REPLY_WINDOW_HOURS = 48  # For showing the countdown only

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None

# ===== UI: Create page =====
@router.get("/bookings/new")
def booking_new_page(
    request: Request,
    item_id: int = Query(..., description="ID of the item to book"),
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
        "title": "Choose booking duration",
        "session_user": request.session.get("user"),
        "item": item,
        "start_default": today.isoformat(),
        "end_default": (today + timedelta(days=1)).isoformat(),
        "days_default": 1,
    }
    return request.app.templates.TemplateResponse("booking_new.html", ctx)

# ===== Create booking =====
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
            db, bk.owner_id, "New booking request",
            f"On '{item.title}'. Click to view details.",
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

# ===== Flow page =====
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
    item   = db.get(Item, bk.item_id)
    owner  = db.get(User, bk.owner_id)
    renter = db.get(User, bk.renter_id)

    # Owner payouts activation state to enable online payment
    owner_pe = bool(getattr(owner, "payouts_enabled", False)) if owner else False

    # Dispute window (48h) after return
    dispute_deadline = None
    if getattr(bk, "returned_at", None):
        try:
            dispute_deadline = bk.returned_at + timedelta(hours=DISPUTE_WINDOW_HOURS)
        except Exception:
            dispute_deadline = None

    # === Fees & taxes (احسبها قبل ctx) ===
    try:
        rent_amount = float(getattr(bk, "total_amount", 0.0) or 0.0)
    except Exception:
        rent_amount = 0.0

    pct         = float(os.getenv("STRIPE_PROCESSING_PCT", "0.029") or 0.029)
    fixed_cents = int(os.getenv("STRIPE_PROCESSING_FIXED_CENTS", "30") or 30)
    processing_fee       = round(rent_amount * pct + (fixed_cents / 100.0), 2)
    subtotal_before_tax  = round(rent_amount + processing_fee, 2)
    taxes_ctx            = _adapter_taxes_for_request(request, subtotal_before_tax)

    ctx = {
        "request": request,
        "title": "Booking",
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
        "dispute_deadline_iso": _iso(dispute_deadline),
        "renter_reply_hours": RENTER_REPLY_WINDOW_HOURS,

        # ↓↓↓ هذه القيم الآن جاهزة لأننا حسبناها فوق
        "rent_amount": rent_amount,
        "processing_fee": processing_fee,
        "subtotal_before_tax": subtotal_before_tax,
        "taxes": taxes_ctx,
        "CURRENCY": (os.getenv("CURRENCY", "CAD") or "CAD").upper(),
        "STRIPE_PROCESSING_PCT": pct,
        "STRIPE_PROCESSING_FIXED_CENTS": fixed_cents,
    }

    return request.app.templates.TemplateResponse("booking_flow.html", ctx)


# ===== Owner decision =====
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
        push_notification(db, bk.renter_id, "Booking rejected",
                          f"Your request on '{item.title}' was rejected.",
                          f"/bookings/flow/{bk.id}", "booking")
        return redirect_to_flow(bk.id)

    bk.owner_decision = "accepted"

    # Default deposit = 5 × daily price if the owner didn’t enter a number
    default_deposit = (item.price_per_day or 0) * 5
    amount = int(deposit_amount or 0)
    if amount <= 0:
        amount = default_deposit

    bk.deposit_amount = max(0, amount)
    bk.accepted_at = datetime.utcnow()
    bk.timeline_owner_decided_at = datetime.utcnow()
    bk.status = "accepted"
    db.commit()

    dep_txt = f" with a {bk.deposit_amount}$ deposit" if (bk.deposit_amount or 0) > 0 else ""
    push_notification(db, bk.renter_id, "Booking accepted",
                      f"On '{item.title}'. Choose a payment method{dep_txt}.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# ===== Choose payment method =====
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
        push_notification(db, bk.owner_id, "Renter chose cash",
                          f"Booking '{item.title}'. Payment will be made on pickup.",
                          f"/bookings/flow/{bk.id}", "booking")
        return redirect_to_flow(bk.id)

    bk.payment_method = "online"
    bk.timeline_payment_method_chosen_at = datetime.utcnow()
    db.commit()
    push_notification(db, bk.owner_id, "Online payment chosen",
                      f"Booking '{item.title}'. Waiting for renter to pay.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# ===== Online payment — block if owner hasn’t enabled payouts =====
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

    # ✅ Simultaneous payment for rent + deposit in a single session
    return RedirectResponse(url=f"/api/stripe/checkout/all/{booking_id}", status_code=303)

# ===== Renter confirms receipt =====
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

    push_notification(db, bk.owner_id, "Renter picked up the item",
                      f"'{item.title}'. Reminder about the return date.",
                      f"/bookings/flow/{bk.id}", "booking")
    push_notification(db, bk.renter_id, "Pickup confirmed",
                      f"Don’t forget to return '{item.title}' on time.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# ===== Owner confirms delivery =====
@router.post("/bookings/{booking_id}/owner/confirm_delivered")
def owner_confirm_delivered(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    Allows the owner to mark that the item was delivered to the renter.
    - Captures the rent payment if it was online (manual capture).
    - Changes the status to picked_up.
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can confirm delivery")
    if bk.status not in ("paid",):
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

    push_notification(db, bk.renter_id, "Item delivered",
                      f"The owner delivered '{item.title}'. Enjoy your rental.",
                      f"/bookings/flow/{bk.id}", "booking")
    return redirect_to_flow(bk.id)

# ===== Shortcut to open a deposit dispute =====
@router.post("/bookings/{booking_id}/owner/open_deposit_issue")
def owner_open_deposit_issue(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    Shortcut that redirects to the dispute form located in routes_deposits.py
    The real POST is at: /deposits/{booking_id}/report
    """
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner")
    return RedirectResponse(url=f"/deposits/{bk.id}/report", status_code=303)

# ===== API returns the dispute window and renter-reply window in ISO =====
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
    if getattr(bk, "returned_at", None):
        try:
            dispute_deadline = bk.returned_at + timedelta(hours=DISPUTE_WINDOW_HOURS)
        except Exception:
            dispute_deadline = None

    return _json({
        "dispute_deadline_iso": _iso(dispute_deadline),
        "renter_reply_window_hours": RENTER_REPLY_WINDOW_HOURS,
    })

# ======= Old aliases (left for compatibility) =======
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

    # Quick accept without manual input: fill default deposit
    default_deposit = (item.price_per_day or 0) * 5
    if (bk.deposit_amount or 0) <= 0:
        bk.deposit_amount = default_deposit

    bk.status = "accepted"
    bk.owner_decision = "accepted"
    bk.accepted_at = datetime.utcnow()
    bk.timeline_owner_decided_at = datetime.utcnow()
    db.commit()
    push_notification(db, bk.renter_id, "Booking accepted",
                      f"On '{item.title}'. Choose a payment method.",
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
    push_notification(db, bk.renter_id, "Booking rejected",
                      f"Your request on '{item.title}' was rejected.",
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
    push_notification(db, bk.owner_id, "Renter chose cash",
                      f"Booking '{item.title}'. Payment will be made on pickup.",
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

    # ✅ Simultaneous payment for rent + deposit
    return RedirectResponse(url=f"/api/stripe/checkout/all/{booking_id}", status_code=303)

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
    push_notification(db, bk.owner_id, "Renter picked up the item",
                      f"'{item.title}'. Reminder about the return date.",
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

    push_notification(db, bk.owner_id, "Return marked",
                      f"The item '{item.title}' was returned. Waiting for admin review of the deposit.",
                      f"/bookings/flow/{bk.id}", "deposit")
    push_notification(db, bk.renter_id, "Deposit under review",
                      f"You will be notified after the admin reviews the deposit for booking '{item.title}'.",
                      f"/bookings/flow/{bk.id}", "deposit")
    notify_admins(db, "Deposit review required",
                  f"Booking #{bk.id} needs a deposit decision.", f"/bookings/flow/{bk.id}")
    return _redir(bk.id)

# ===== Booking JSON state =====
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

# ===== Booking list page =====
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
        title = "Bookings on my items"
    else:
        q = q.filter(Booking.renter_id == user.id)
        title = "My bookings"

    q = q.order_by(_booking_order_col())
    bookings = q.all()

    return request.app.templates.TemplateResponse(
        "booking_index.html",  # ✅ Name adjusted (was bookings_index.html)
        {
            "request": request,
            "title": title,
            "session_user": request.session.get("user"),
            "bookings": bookings,
            "view": view,
        },
    )

# ===== Quick route to manually create a deposit authorization =====
@router.post("/api/stripe/hold/{booking_id}")
def api_create_deposit_hold(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    Creates a manual-capture PaymentIntent in CAD for the deposit if missing
    and stores the identifier in both fields (deposit_hold_intent_id and deposit_hold_id).
    Note: this route is **POST**. Any GET request will return Method Not Allowed.
    """
    require_auth(user)
    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")

    ok = _ensure_deposit_hold(bk)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to create deposit hold")

    db.commit()
    return {"ok": True, "deposit_hold_intent_id": _get_deposit_pi_id(bk)}

# ✅ Stripe Checkout state for buttons in the flow UI
@router.get("/api/stripe/checkout/state/{booking_id}")
def api_stripe_checkout_state(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not (is_renter(user, bk) or is_owner(user, bk)):
        raise HTTPException(status_code=403, detail="Forbidden")

    # We consider rent successful if online_status is one of these values (per your logic/webhook)
    rent_ok = str(getattr(bk, "online_status", "") or "").lower() in (
        "authorized", "captured", "succeeded", "paid"
    )
    # We consider deposit held if deposit_status is one of these values
    dep_ok = str(getattr(bk, "deposit_status", "") or "").lower() in (
        "held", "authorized"
    )

    ready = bool(rent_ok and dep_ok)  # If both succeeded → ready for the next step
    return _json({
        "rent_authorized": rent_ok,
        "deposit_held": dep_ok,
        "ready_for_pickup": ready
    })


@router.get("/bookings/flow/{booking_id}/next")
def booking_flow_next(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    # For now we just redirect to a “next step” (adjust the destination later as you like)
    require_auth(user)
    _ = require_booking(db, booking_id)
    return RedirectResponse(url=f"/bookings/flow/{booking_id}?ready=1", status_code=303)

# ===== Shims for separate payment routes → redirect to the unified route =====
@router.post("/api/stripe/checkout/rent/{booking_id}")
def shim_checkout_rent(booking_id: int):
    return RedirectResponse(url=f"/api/stripe/checkout/all/{booking_id}?only=rent", status_code=303)

@router.post("/api/stripe/checkout/deposit/{booking_id}")
def shim_checkout_deposit(booking_id: int):
    return RedirectResponse(url=f"/api/stripe/checkout/all/{booking_id}?only=deposit", status_code=303)
