# app/payout_connect.py
import os, stripe
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import User

router = APIRouter(prefix="/payout", tags=["payouts"])
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

def current_user(request: Request, db: Session):
    s = request.session.get("user")
    return db.query(User).get(s["id"]) if s else None

@router.get("/connect/start")
def connect_start(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return RedirectResponse("/login", status_code=303)

    if not u.stripe_account_id:
        acct = stripe.Account.create(type="express")
        u.stripe_account_id = acct.id
        db.commit()

    refresh_url = str(request.url_for("connect_refresh"))
    return_url  = str(request.url_for("connect_return"))

    link = stripe.AccountLink.create(
        account=u.stripe_account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )
    return RedirectResponse(link.url, status_code=303)

@router.get("/connect/refresh", name="connect_refresh")
def connect_refresh():
    return RedirectResponse("/payout/connect/start", status_code=303)

@router.get("/connect/return", name="connect_return")
def connect_return(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return RedirectResponse("/login", status_code=303)
    acct = stripe.Account.retrieve(u.stripe_account_id)
    u.payouts_enabled = bool(acct.get("payouts_enabled", False))
    db.commit()
    return RedirectResponse("/payout/settings", status_code=303)
