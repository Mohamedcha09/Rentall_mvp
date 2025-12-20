# app/payments.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Item

router = APIRouter()

# ===== Helpers =====
def require_login(request: Request):
    return request.session.get("user")

def require_approved(request: Request):
    u = request.session.get("user")
    return u and u.get("status") == "approved"

# ================================
# Owner account to receive funds (UI)
# ================================
@router.get("/wallet/connect")
def wallet_connect(request: Request):
    """
    A simplified page that shows a (Stripe Connect) button — keep your current template if you wish,
    but the button will redirect to the real /payout/connect/start.
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    return request.app.templates.TemplateResponse(
        "wallet_connect.html",
        {
            "request": request,
            "title": "Payout Account Setup",
            "session_user": u,
            "connect_start_url": "/payout/connect/start",
            "connect_refresh_url": "/payout/connect/refresh",
        }
    )

@router.post("/wallet/connect")
def wallet_connect_post(request: Request):
    """
    Support for any old form: immediately redirect to the real start path in payout_connect.py
    """
    return RedirectResponse(url="/payout/connect/start", status_code=303)

# =========================================
# Deposit/checkout page for the renter (Placeholder)
# =========================================
@router.get("/checkout/deposit/{item_id}")
def checkout_deposit(item_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    item = db.query(Item).get(item_id)
    if not item or item.is_active != "yes":
        return RedirectResponse(url="/items", status_code=303)

    # Later: read the real security_deposit from DB if you add the column.
    security_deposit = getattr(item, "security_deposit", None) or 100
    return request.app.templates.TemplateResponse(
        "checkout_deposit.html",
        {
            "request": request,
            "title": "Deposit/Reservation",
            "session_user": u,
            "item": item,
            "security_deposit": security_deposit,
        }
    )

@router.post("/checkout/deposit/{item_id}")
def checkout_deposit_post(item_id: int, request: Request):
    # Later: create Stripe session or deposit authorization.
    return RedirectResponse(url="/my/rentals", status_code=303)

# =====================
# “My dashboards” pages
# =====================
@router.get("/my/rentals")         # As renter
def my_rentals(request: Request):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "my_rentals.html",
        {"request": request, "title": "My Rentals (Renter)", "session_user": u}
    )

@router.get("/my/orders")          # As owner
def my_orders(request: Request):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "my_orders.html",
        {"request": request, "title": "My Orders (Owner)", "session_user": u}
    )

# ================
# Dispute/Report
# ================
@router.get("/dispute/new")
def dispute_new(request: Request):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "dispute_new.html",
        {"request": request, "title": "Open Dispute", "session_user": u}
    )

@router.post("/dispute/new")
def dispute_new_post(request: Request, reason: str = Form(...)):
    # Later: save the dispute in DB and notify admins
    return RedirectResponse(url="/my/rentals", status_code=303)
