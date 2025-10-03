# app/routes_favorites.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Favorite, Item
from .utils import category_label

router = APIRouter()

# عرض صفحة المفضلات
@router.get("/favorites")
def favorites_page(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    favs = (
        db.query(Favorite)
        .filter(Favorite.user_id == user["id"])
        .join(Item)
        .all()
    )

    items = [f.item for f in favs]
    return request.app.templates.TemplateResponse(
        "favorites.html",
        {
            "request": request,
            "title": "مفضلتي",
            "session_user": user,
            "favorites": items,
            "category_label": category_label,
            "favorites_ids": [i.id for i in items],  # تمرير IDs لتمييز القلوب
        }
    )


# API لإضافة/حذف مفضلة
@router.post("/favorites/toggle/{item_id}")
def toggle_favorite(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user:
        return {"ok": False, "error": "login_required"}

    fav = db.query(Favorite).filter(
        Favorite.user_id == user["id"], Favorite.item_id == item_id
    ).first()

    if fav:
        db.delete(fav)
        db.commit()
        return {"ok": True, "action": "removed"}
    else:
        new_fav = Favorite(user_id=user["id"], item_id=item_id)
        db.add(new_fav)
        db.commit()
        return {"ok": True, "action": "added"}