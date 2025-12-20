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
        .filter(
            UserPayoutMethod.user_id == user.id,
            UserPayoutMethod.is_active == True
        )
        .first()
    )

    # 🔴 المنطق النهائي (لا تغيّره)
    show_form = request.query_params.get("edit") == "1" or payout is None

    return request.app.templates.TemplateResponse(
        "payout_settings.html",
        {
            "request": request,
            "user": user,
            "payout": payout,
            "show_form": show_form,
        },
    )

@router.post("/payout/settings")
def save_payout_settings(
    request: Request,
    method: str = Form(...),
    currency: str = Form(...),

    interac_destination: str = Form(None),
    paypal_email: str = Form(None),
    wise_iban: str = Form(None),

    auto_deposit: bool = Form(False),

    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    # =====================================================
    # Determine destination + country
    # =====================================================
    if method == "interac":
        destination = interac_destination
        country = "CA"
    elif method == "paypal":
        destination = paypal_email
        country = "US"
    elif method == "wise":
        destination = wise_iban
        country = "EU"
    else:
        return RedirectResponse("/payout/settings?error=invalid", status_code=303)

    if not destination:
        return RedirectResponse("/payout/settings?error=missing", status_code=303)

    # =====================================================
    # Disable previous payout methods
    # =====================================================
    db.query(UserPayoutMethod).filter(
        UserPayoutMethod.user_id == user.id,
        UserPayoutMethod.is_active == True
    ).update({"is_active": False})

    # =====================================================
    # Create new payout method
    # =====================================================
    payout = UserPayoutMethod(
        user_id=user.id,
        method=method,
        country=country,
        currency=currency,
        destination=destination,
        auto_deposit=auto_deposit if method == "interac" else None,
        is_active=True,
    )

    db.add(payout)

    # =====================================================
    # 🔥 IMPORTANT FIX: enable payouts for the user
    # =====================================================
    user.payouts_enabled = True

    db.commit()

    return RedirectResponse("/payout/settings?saved=1", status_code=303)


# =====================================================
# POST – Remove payout method
# =====================================================
@router.post("/payout/settings/remove")
def remove_payout(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    db.query(UserPayoutMethod).filter(
        UserPayoutMethod.user_id == user.id,
        UserPayoutMethod.is_active == True
    ).update({"is_active": False})

    db.commit()
    return RedirectResponse("/payout/settings", status_code=303)  