# app/payouts.py
import os, stripe
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import User

router = APIRouter()
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

def _me(request: Request): return request.session.get("user")
def _need_login(): return RedirectResponse(url="/login", status_code=303)

@router.get("/payout/settings")
def payout_settings(request: Request, db: Session = Depends(get_db)):
    u = _me(request)
    if not u: return _need_login()
    me: User = db.query(User).get(u["id"])
    return request.app.templates.TemplateResponse(
        "payout_settings.html",
        {"request": request, "title": "إعدادات التحويل", "user": me, "session_user": u,
         "pk": os.environ.get("STRIPE_PUBLISHABLE_KEY")}
    )

@router.post("/payout/connect")
def payout_connect(request: Request, db: Session = Depends(get_db)):
    u = _me(request)
    if not u: return _need_login()
    me: User = db.query(User).get(u["id"])

    # أنشئ حساب Express إن لم يوجد
    if not me.stripe_account_id:
        acct = stripe.Account.create(type="express", country="US", capabilities={"transfers":{"requested":True}})
        me.stripe_account_id = acct["id"]
        db.commit()

    # أنشئ رابط Onboarding
    link = stripe.AccountLink.create(
        account = me.stripe_account_id,
        refresh_url = "http://127.0.0.1:8000/payout/settings",
        return_url  = "http://127.0.0.1:8000/payout/return",
        type="account_onboarding",
    )
    return RedirectResponse(url=link["url"], status_code=303)

@router.get("/payout/return")
def payout_return(request: Request, db: Session = Depends(get_db)):
    u = _me(request)
    if not u: return _need_login()
    me: User = db.query(User).get(u["id"])
    if me and me.stripe_account_id:
        acct = stripe.Account.retrieve(me.stripe_account_id)
        me.payouts_enabled = bool(acct.get("details_submitted") and acct.get("charges_enabled"))
        db.commit()
    return RedirectResponse(url="/payout/settings", status_code=303)
