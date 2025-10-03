# app/routes_favorites.py
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .database import get_db
from .models import Favorite, Item

router = APIRouter()

def _require_user_id(request: Request) -> int | None:
    u = request.session.get("user")
    return u["id"] if u and "id" in u else None

@router.get("/favorites")
def my_favorites(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login?next=/favorites", status_code=303)

    favs = (
        db.query(Favorite)
        .filter(Favorite.user_id == user_id)
        .order_by(desc(Favorite.created_at))
        .all()
    )
    item_ids = [f.item_id for f in favs]
    items = []
    if item_ids:
        items = (
            db.query(Item)
            .filter(Item.id.in_(item_ids))
            .order_by(desc(Item.created_at))
            .all()
        )

    return request.app.templates.TemplateResponse(
        "favorites.html",
        {
            "request": request,
            "title": "مفضلاتي",
            "session_user": request.session.get("user"),
            "items": items,
        },
    )

@router.post("/favorites/toggle")
def toggle_favorite(
    request: Request,
    db: Session = Depends(get_db),
    item_id: int = Form(...)
):
    user_id = _require_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    fav = (
        db.query(Favorite)
        .filter(Favorite.user_id == user_id, Favorite.item_id == item_id)
        .first()
    )

    if fav:
        # إلغاء المفضلة
        db.delete(fav)
        db.commit()
    else:
        # إضافة مفضلة
        new_fav = Favorite(user_id=user_id, item_id=item_id)
        db.add(new_fav)
        db.commit()

    # ارجع لنفس الصفحة السابقة لو متاح
    referer = request.headers.get("referer") or "/"
    return RedirectResponse(url=referer, status_code=303)