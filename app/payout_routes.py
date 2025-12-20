# app/payout_routes.py
import os
from typing import Optional

import stripe
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter(tags=["payouts"])

# ===== Helpers =====
def _require_login(request: Request) -> Optional[dict]:
    return request.session.get("user")

def _stripe_key_ok() -> bool:
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    return key.startswith("sk_test_") or key.startswith("sk_live_")

def _refresh_connect_status(db: Session, user: User) -> None:
    """
    Updates payouts_enabled status from Stripe for the user’s connected account.
    Called when returning from Stripe (return/refresh).
    """
    if not user or not user.stripe_account_id:
        return
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    if not key:
        return
    try:
        stripe.api_key = key
        acct = stripe.Account.retrieve(user.stripe_account_id)
        if hasattr(user, "payouts_enabled"):
            user.payouts_enabled = bool(getattr(acct, "payouts_enabled", False))
            db.add(user)
            db.commit()
    except Exception:
        # Quietly ignore errors — the page will show the user that linking is not complete
        pass


# ===== 2) “Start linking” button (redirects to pay_api route) =====
@router.post("/payout/connect/start")
def payout_connect_start_proxy(request: Request):
    """
    This is just a proxy to simplify calling from the template.
    It redirects directly to the Stripe route inside pay_api.py
    """
    return RedirectResponse(url="/api/stripe/connect/start", status_code=303)


# ===== 3) Return/refresh routes from Stripe (compatible with pay_api.py) =====
@router.get("/payouts/return")
def payouts_return(request: Request, db: Session = Depends(get_db)):
    """
    Stripe returns to this route after completing the onboarding.
    We update the local account status, then send the owner back to the settings page.
    """
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    db_user = db.query(User).get(sess["id"])
    _refresh_connect_status(db, db_user)

    # Send back to the page (it will display the updated status)
    return RedirectResponse(url="/payout/settings", status_code=303)


@router.get("/payouts/refresh")
def payouts_refresh(request: Request, db: Session = Depends(get_db)):
    """
    Stripe calls this when pressing “Back” during onboarding.
    We return the user to the settings page and try to refresh the status.
    """
    sess = _require_login(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    db_user = db.query(User).get(sess["id"])
    _refresh_connect_status(db, db_user)

    return RedirectResponse(url="/payout/settings", status_code=303)


# ===== 4) Key setup health check (optional to show a helpful message) =====
@router.get("/payout/debug-key")
def payout_debug_key():
    key = os.getenv("STRIPE_SECRET_KEY", "") or ""
    if not key:
        return HTMLResponse("<h4>STRIPE_SECRET_KEY is not set</h4>", status_code=500)
    mode = "TEST" if key.startswith("sk_test_") else ("LIVE" if key.startswith("sk_live_") else "UNKNOWN")
    return HTMLResponse(f"<pre>Stripe key is set.\nMode: {mode}\nValue (masked): {key[:8]}...{key[-4:]}</pre>")
