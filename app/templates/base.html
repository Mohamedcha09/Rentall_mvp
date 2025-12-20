# app/payout_connect.py

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserPayoutMethod

router = APIRouter()

# =====================================================
# Helpers
# =====================================================
def get_current_user(request: Request, db: Session) -> User | None:
    sess = request.session.get("user")
    if not sess:
        return None
    return db.query(User).get(sess.get("id"))

# =====================================================
# GET – Payout settings page
# =====================================================
@router.get("/payout/settings", response_class=HTMLResponse)
def payout_settings(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    payout = (
        db.query(UserPayoutMethod)
        .filter(UserPayoutMethod.user_id == user.id, UserPayoutMethod.is_active == True)
        .first()
    )

    return request.app.templates.TemplateResponse(
        "payout_connect.html",
        {
            "request": request,
            "user": user,
            "payout": payout,
        },
    )

# =====================================================
# POST – Save payout preference
# =====================================================
@router.post("/payout/settings")
def save_payout_settings(
    request: Request,
    country: str = Form(...),
    method: str = Form(...),
    destination: str = Form(...),
    currency: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    # Disable previous methods
    db.query(UserPayoutMethod).filter(
        UserPayoutMethod.user_id == user.id,
        UserPayoutMethod.is_active == True
    ).update({"is_active": False})

    payout = UserPayoutMethod(
        user_id=user.id,
        method=method,
        country=country,
        currency=currency,
        destination=destination,
        is_active=True,
    )

    db.add(payout)
    db.commit()

    return RedirectResponse("/payout/settings?saved=1", status_code=303)
