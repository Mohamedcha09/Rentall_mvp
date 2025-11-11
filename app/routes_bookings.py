# app/routes_bookings.py
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

# ===== utili_geo (اختياري: نتعامل مع اختلاف الأسماء بين المشاريع) =====
try:
    from .utili_geo import (
        geo_from_request as _geo_req,
        locate_from_request as _geo_locate,
        locate_from_session as _geo_session,
    )
except Exception:
    _geo_req = _geo_locate = _geo_session = None

# ===== utili_tax (اختياري) =====
try:
    from .utili_tax import compute_order_taxes as _tax_order
except Exception:
    _tax_order = None

try:
    from .utili_tax import compute_taxes as _tax_compute
except Exception:
    _tax_compute = None

try:
    from .utili_tax import compute_ca_taxes as _tax_ca
except Exception:
    _tax_ca = None


# ========================================
# Geo adapters
# ========================================
def _adapter_geo_from_request(request: Request) -> dict:
    """
    يرجّع {"country": .., "sub": ..}
    يدعم override عبر ?loc=CA أو ?loc=CA-QC ويكمل sub عند توفرها.
    """
    # 0) نقرأ لقطة من الحجز/المستخدم لو متاحة في request.state (نملأها لاحقًا داخل flow)
    bk = getattr(request.state, "booking", None)
    renter = getattr(request.state, "renter", None)

    # 1) ?loc=...
    loc_q = request.query_params.get("loc")
    if loc_q:
        p = loc_q.replace("_", "-").strip().upper().split("-")
        country = p[0] if p else None
        sub = p[1] if len(p) > 1 else None
        # إن كانت sub ناقصة، نحاول تكملتها من الحجز/المستأجر/الجلسة
        if country and not sub:
            # من لقطة الحجز
            if bk:
                s = (getattr(bk, "loc_sub", "") or "").strip().upper()
                if s:
                    sub = s
            # من حساب المستأجر
            if not sub and renter:
                s = (getattr(renter, "region", None) or getattr(renter, "state", None) or
                     getattr(renter, "geo_region", None) or "")
                sub = str(s).strip().upper() or None
            # من الجلسة
            if not sub:
                s = getattr(request, "session", {}) or {}
                s = (s.get("geo_region") or s.get("region") or s.get("geo", {}).get("region") or "")
                sub = str(s).strip().upper() or None
        return {"country": country, "sub": sub}

    # 2) utili_geo إن وُجدت
    for fn in (_geo_req, _geo_locate, _geo_session):
        if callable(fn):
            try:
                g = fn(request)
                if isinstance(g, dict):
                    country = (g.get("country") or g.get("cc") or "").upper() or None
                    sub = (g.get("sub") or g.get("region") or g.get("prov") or "").upper() or None
                    if country:
                        return {"country": country, "sub": sub}
            except Exception:
                pass

    # 3) الجلسة
    s = getattr(request, "session", {}) or {}
    country = (s.get("geo_country") or s.get("country") or s.get("geo", {}).get("country") or "")
    region  = (s.get("geo_region")  or s.get("region")  or s.get("geo", {}).get("region")  or "")
    country = (str(country).upper().strip() or None)
    sub     = (str(region).upper().strip()  or None)
    if country:
        return {"country": country, "sub": sub}

    # 4) fallback قديم
    if s.get("loc"):
        p = str(s["loc"]).upper().split("-")
        return {"country": p[0], "sub": (p[1] if len(p) > 1 else None)}

    return {"country": None, "sub": None}


def _loc_qs_for_user(u: Optional[User]) -> str:
    if not u:
        return ""
    country = (getattr(u, "country", None) or getattr(u, "geo_country", None) or "").strip().upper()
    sub     = (getattr(u, "region", None)  or getattr(u, "state", None) or getattr(u, "geo_region", None) or "").strip().upper()
    if country and sub:
        return f"?loc={country}-{sub}"
    if country:
        return f"?loc={country}"
    return ""


def _loc_qs_for_booking(bk: Booking) -> str:
    c = (getattr(bk, "loc_country", "") or "").strip().upper()
    s = (getattr(bk, "loc_sub", "") or "").strip().upper()
    if c and s:
        return f"?loc={c}-{s}"
    if c:
        return f"?loc={c}"
    return ""


# ========================================
# Taxes
# ========================================
def _adapter_taxes_for_request(request: Request, subtotal: float) -> dict:
    """
    يوحّد مخرجات الضرائب إلى شكل واحد يفهمه القالب.
    """
    currency = (os.getenv("CURRENCY", "CAD") or "CAD").upper()
    geo = _adapter_geo_from_request(request)
    country = (geo.get("country") or "").upper() or None
    sub     = (geo.get("sub") or "").upper() or None

    # 1) utili_tax: compute_order_taxes
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

    # 2) utili_tax: compute_taxes
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

    # 3) مثال كندا
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

    # 4) فشل → نتركها لسترايب
    return {
        "mode": "stripe",
        "currency": currency, "country": country, "sub": sub,
        "tax_lines": [], "tax_total": None, "grand_total": subtotal,
    }


# ========================================
# Helpers
# ========================================
def _best_loc_qs(bk: Booking, renter: Optional[User]=None) -> str:
    """
    نختار أفضل استعلام للموقع بالترتيب:
    1) لقطة الحجز (loc_country + loc_sub)
    2) لقطة الحجز (loc_country فقط)
    3) حساب المستأجر (country + region/state)
    وإلا: "".
    """
    qs = _loc_qs_for_booking(bk)
    if qs:
        return qs
    if renter:
        qs = _loc_qs_for_user(renter)
        if qs:
            return qs
    return ""
def redirect_to_flow_with_loc(bk: Booking, renter: Optional[User]=None) -> RedirectResponse:
    return RedirectResponse(
        url=f"/bookings/flow/{bk.id}{_best_loc_qs(bk, renter)}",
        status_code=303
    )

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


# ========================================
# Stripe helpers
# ========================================
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


# Deposit PI unifier
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

def _ensure_deposit_hold(bk: Booking) -> bool:
    """
    ينشئ PaymentIntent (manual capture) للتأمين إن لم يكن موجودًا.
    """
    try:
        import stripe
        sk = os.getenv("STRIPE_SECRET_KEY", "")
        if not sk:
            return False
        stripe.api_key = sk

        if _get_deposit_pi_id(bk):
            return True

        amount = int(getattr(bk, "deposit_amount", 0) or 0)
        if amount <= 0:
            return False

        pi = stripe.PaymentIntent.create(
            amount=amount * 100,
            currency=(os.getenv("CURRENCY", "CAD") or "CAD").lower(),
            capture_method="manual",
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


# ========================================
# Policy / constants
# ========================================
DISPUTE_WINDOW_HOURS = 48
RENTER_REPLY_WINDOW_HOURS = 48

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# ========================================
# UI: Create page
# ========================================
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


# ========================================
# Create booking
# ========================================
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
        renter = db.get(User, bk.renter_id)
        return redirect_to_flow_with_loc(bk, renter)


    except HTTPException:
        raise
    except Exception:
        item_id_for_redirect = pick("item_id", "item", "itemId", default="")
        return RedirectResponse(
            url=f"/bookings/new?item_id={item_id_for_redirect}&err=invalid",
            status_code=303
        )


# ========================================
# Flow page
# ========================================
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

    # ⬅️ نوفر الحجز/المستأجر لـ _adapter_geo_from_request (انظر الخطوة 2)
    request.state.booking = bk
    request.state.renter = renter

    # ✅ تطبيع الـURL: إن دخلت بـ ?loc=CA فقط ولدينا sub معروف → نعيد التوجيه إلى ?loc=CA-SUB
    desired_qs = _best_loc_qs(bk, renter)
    current_loc = request.query_params.get("loc")
    if desired_qs and (current_loc is None or desired_qs != f"?loc={current_loc}"):
        # نحتفظ بباقي الاستعلامات إن وُجدت
        base = f"/bookings/flow/{bk.id}"
        others = [(k, v) for k, v in request.query_params.items() if k != "loc"]
        tail = "&".join([f"{k}={v}" for k, v in others])
        url = f"{base}{desired_qs}" + (f"&{tail}" if tail else "")
        return RedirectResponse(url=url, status_code=303)

    owner_pe = bool(getattr(owner, "payouts_enabled", False)) if owner else False

    dispute_deadline = None
    if getattr(bk, "returned_at", None):
        try:
            dispute_deadline = bk.returned_at + timedelta(hours=DISPUTE_WINDOW_HOURS)
        except Exception:
            dispute_deadline = None

    # === Fees & taxes كالعادة…
    try:
        rent_amount = float(getattr(bk, "total_amount", 0.0) or 0.0)
    except Exception:
        rent_amount = 0.0

    pct         = float(os.getenv("STRIPE_PROCESSING_PCT", "0.029") or 0.029)
    fixed_cents = int(os.getenv("STRIPE_PROCESSING_FIXED_CENTS", "30") or 30)
    processing_fee      = round(rent_amount * pct + (fixed_cents / 100.0), 2)
    subtotal_before_tax = round(rent_amount + processing_fee, 2)
    taxes_ctx           = _adapter_taxes_for_request(request, subtotal_before_tax)

    # 🗺️ Snapshot للموقع: نحفظ country و sub فورًا إن لم تكن محفوظة
    geo = _adapter_geo_from_request(request)
    try:
        updated = False
        if not getattr(bk, "loc_country", None) and geo.get("country"):
            bk.loc_country = geo.get("country")
            updated = True
        if not getattr(bk, "loc_sub", None) and geo.get("sub"):
            bk.loc_sub = geo.get("sub")
            updated = True
        if updated:
            db.commit()
    except Exception:
        pass


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

        "rent_amount": rent_amount,
        "processing_fee": processing_fee,
        "subtotal_before_tax": subtotal_before_tax,
        "taxes": taxes_ctx,
        "CURRENCY": (os.getenv("CURRENCY", "CAD") or "CAD").upper(),
        "STRIPE_PROCESSING_PCT": pct,
        "STRIPE_PROCESSING_FIXED_CENTS": fixed_cents,
    }
    return request.app.templates.TemplateResponse("booking_flow.html", ctx)


# ========================================
# Owner decision
# ========================================
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
        push_notification(
            db, bk.renter_id, "Booking rejected",
            f"Your request on '{item.title}' was rejected.",
            f"/bookings/flow/{bk.id}", "booking"
        )
        renter = db.get(User, bk.renter_id)
        return redirect_to_flow_with_loc(bk, renter)


    bk.owner_decision = "accepted"

    # Default deposit
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
    # ✅ نختار أفضل استعلام للموقع: من لقطة الحجز أو من حساب المستأجر
    renter = db.get(User, bk.renter_id)
    qs = _loc_qs_for_booking(bk) or _loc_qs_for_user(renter)
    link = f"/bookings/flow/{bk.id}{qs}"

    push_notification(
        db, bk.renter_id, "Booking accepted",
        f"On '{item.title}'. Choose a payment method{dep_txt}.",
        link,
        "booking"
    )
    renter = db.get(User, bk.renter_id)
    return redirect_to_flow_with_loc(bk, renter)



# ========================================
# Renter chooses payment
# ========================================
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
        push_notification(
            db, bk.owner_id, "Renter chose cash",
            f"Booking '{item.title}'. Payment will be made on pickup.",
            f"/bookings/flow/{bk.id}", "booking"
        )
        renter = db.get(User, bk.renter_id)
        return redirect_to_flow_with_loc(bk, renter)


    bk.payment_method = "online"
    bk.timeline_payment_method_chosen_at = datetime.utcnow()
    db.commit()
    push_notification(
        db, bk.owner_id, "Online payment chosen",
        f"Booking '{item.title}'. Waiting for renter to pay.",
        f"/bookings/flow/{bk.id}", "booking"
    )
    renter = db.get(User, bk.renter_id)
    return redirect_to_flow_with_loc(bk, renter)



# ========================================
# Renter pays online (block if owner payouts disabled)
# ========================================
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

    # دفع الإيجار + التأمين معًا
    return RedirectResponse(url=f"/api/stripe/checkout/all/{booking_id}", status_code=303)


# ========================================
# Renter confirms receipt
# ========================================
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

    push_notification(
        db, bk.owner_id, "Renter picked up the item",
        f"'{item.title}'. Reminder about the return date.",
        f"/bookings/flow/{bk.id}", "booking"
    )
    push_notification(
        db, bk.renter_id, "Pickup confirmed",
        f"Don’t forget to return '{item.title}' on time.",
        f"/bookings/flow/{bk.id}", "booking"
    )
    renter = db.get(User, bk.renter_id)
    return redirect_to_flow_with_loc(bk, renter)



# ========================================
# Owner confirms delivery
# ========================================
@router.post("/bookings/{booking_id}/owner/confirm_delivered")
def owner_confirm_delivered(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner can confirm delivery")
    if bk.status not in ("paid",):
        renter = db.get(User, bk.renter_id)
        return redirect_to_flow_with_loc(bk, renter)


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

    push_notification(
        db, bk.renter_id, "Item delivered",
        f"The owner delivered '{item.title}'. Enjoy your rental.",
        f"/bookings/flow/{bk.id}", "booking"
    )
    renter = db.get(User, bk.renter_id)
    return redirect_to_flow_with_loc(bk, renter)



# ========================================
# Deposit dispute shortcut
# ========================================
@router.post("/bookings/{booking_id}/owner/open_deposit_issue")
def owner_open_deposit_issue(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    bk = require_booking(db, booking_id)
    if not is_owner(user, bk):
        raise HTTPException(status_code=403, detail="Only owner")
    return RedirectResponse(url=f"/deposits/{bk.id}/report", status_code=303)


# ========================================
# Deadlines JSON
# ========================================
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


# ========================================
# Old aliases (back-compat)
# ========================================
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

    default_deposit = (item.price_per_day or 0) * 5
    if (bk.deposit_amount or 0) <= 0:
        bk.deposit_amount = default_deposit

    bk.status = "accepted"
    bk.owner_decision = "accepted"
    bk.accepted_at = datetime.utcnow()
    bk.timeline_owner_decided_at = datetime.utcnow()
    db.commit()

    renter = db.get(User, bk.renter_id)
    qs = _loc_qs_for_booking(bk) or _loc_qs_for_user(renter)
    link = f"/bookings/flow/{bk.id}{qs}"
    push_notification(
        db, bk.renter_id, "Booking accepted",
        f"On '{item.title}'. Choose a payment method.",
        link,
        "booking"
    )
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

    push_notification(
        db, bk.renter_id, "Booking rejected",
        f"Your request on '{item.title}' was rejected.",
        f"/bookings/flow/{bk.id}", "booking"
    )
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

    push_notification(
        db, bk.owner_id, "Renter chose cash",
        f"Booking '{item.title}'. Payment will be made on pickup.",
        f"/bookings/flow/{bk.id}", "booking"
    )
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
    push_notification(
        db, bk.owner_id, "Renter picked up the item",
        f"'{item.title}'. Reminder about the return date.",
        f"/bookings/flow/{bk.id}", "booking"
    )
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
    return _redir(bk.id)


# ========================================
# Stripe checkout state (UI helper)
# ========================================
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

    rent_ok = str(getattr(bk, "online_status", "") or "").lower() in (
        "authorized", "captured", "succeeded", "paid"
    )
    dep_ok = str(getattr(bk, "deposit_status", "") or "").lower() in (
        "held", "authorized"
    )

    ready = bool(rent_ok and dep_ok)
    return _json({
        "rent_authorized": rent_ok,
        "deposit_held": dep_ok,
        "ready_for_pickup": ready
    })


# ========================================
# Next step redirect (placeholder)
# ========================================
@router.get("/bookings/flow/{booking_id}/next")
def booking_flow_next(
    booking_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_auth(user)
    _ = require_booking(db, booking_id)
    return RedirectResponse(url=f"/bookings/flow/{booking_id}?ready=1", status_code=303)


# ========================================
# Shims
# ========================================
@router.post("/api/stripe/checkout/rent/{booking_id}")
def shim_checkout_rent(booking_id: int):
    return RedirectResponse(url=f"/api/stripe/checkout/all/{booking_id}?only=rent", status_code=303)

@router.post("/api/stripe/checkout/deposit/{booking_id}")
def shim_checkout_deposit(booking_id: int):
    return RedirectResponse(url=f"/api/stripe/checkout/all/{booking_id}?only=deposit", status_code=303)
