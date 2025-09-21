# app/admin_badges.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import User

router = APIRouter()

@router.get("/admin/badges/{user_id}")
def admin_badges_form(user_id: int, request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u or u.get("role") != "admin":
        return RedirectResponse(url="/", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin/users", status_code=303)

    return request.app.templates.TemplateResponse(
        "admin_badges.html",
        {
            "request": request,
            "title": "إدارة شارات المستخدم",
            "session_user": u,
            "target_user": user,
        }
    )

@router.post("/admin/badges/{user_id}")
def admin_badges_save(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    badge_new_yellow: str = Form("off"),
    badge_pro_green: str = Form("off"),
    badge_pro_gold: str = Form("off"),
    badge_purple_trust: str = Form("off"),
    badge_renter_green: str = Form("off"),
    badge_orange_stars: str = Form("off"),
):
    u = request.session.get("user")
    if not u or u.get("role") != "admin":
        return RedirectResponse(url="/", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return RedirectResponse(url="/admin/users", status_code=303)

    user.badge_new_yellow   = (badge_new_yellow == "on")
    user.badge_pro_green    = (badge_pro_green == "on")
    user.badge_pro_gold     = (badge_pro_gold == "on")
    user.badge_purple_trust = (badge_purple_trust == "on")
    user.badge_renter_green = (badge_renter_green == "on")
    user.badge_orange_stars = (badge_orange_stars == "on")

    db.commit()

    return RedirectResponse(url=f"/admin/badges/{user.id}", status_code=303)
