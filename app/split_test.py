# app/split_test.py
import os
import stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter()

def _set_api_key():
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not (key.startswith("sk_test_") or key.startswith("sk_live_")):
        raise HTTPException(500, "STRIPE_SECRET_KEY is missing/invalid")
    stripe.api_key = key

def _base(request: Request) -> str:
    b = (os.getenv("SITE_URL") or "").strip().rstrip("/")
    if b:
        return b
    return f"{request.url.scheme}://{request.url.hostname}"

def _pct(amount_cents: int, fee_pct: float) -> int:
    return int(round(amount_cents * (float(fee_pct) / 100.0)))

@router.get("/split/test")
def split_test_checkout(
    request: Request,
    db: Session = Depends(get_db),
    amount: int = 2000,     # 2000 = 20.00 (بالسنت)
    currency: str | None = None,
):
    """
    تجربة دفع مع تقسيم المبلغ:
    - إن كان charges_enabled=True -> Destination charge + application_fee_amount
    - وإلا: (fallback) تحصيل على المنصّة (لكن غالبًا لن نحتاجه عندك الآن)
    """
    _set_api_key()

    sess_user = request.session.get("user")
    if not sess_user:
        return RedirectResponse("/login", status_code=303)

    user = db.query(User).get(sess_user["id"])
    if not user or not getattr(user, "stripe_account_id", None):
        return JSONResponse({"error": "no_connected_account"}, status_code=400)

    acct_id = user.stripe_account_id
    cur     = (currency or os.getenv("CURRENCY") or "cad").lower()
    fee_pct = float(os.getenv("PLATFORM_FEE_PCT") or 10)   # نسبة عمولة المنصّة %
    app_fee = _pct(amount, fee_pct)                        # بالسنت

    # نفحص حالة الحساب (عندك True)
    acct = stripe.Account.retrieve(acct_id)
    charges_enabled = bool(getattr(acct, "charges_enabled", False))

    base = _base(request)
    success = f"{base}/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel  = f"{base}/cancel"

    if charges_enabled:
        # ✅ Destination charge: الأموال تُحصّل لحساب البائع مباشرة + عمولة المنصّة
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success,
            cancel_url=cancel,
            line_items=[{
                "price_data": {
                    "currency": cur,
                    "product_data": {"name": "Test split order"},
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            payment_intent_data={
                "application_fee_amount": app_fee,
                "transfer_data": {"destination": acct_id},
            },
            metadata={"split_mode": "destination_charge", "acct": acct_id, "fee_pct": str(fee_pct)},
        )
        return RedirectResponse(session.url, status_code=303)

    # (اختياري) لو حبيت تفعّل Fallback لاحقًا، نضيفه هنا
    return JSONResponse({"error": "charges_enabled=false; enable charges or add fallback flow"}, status_code=400)