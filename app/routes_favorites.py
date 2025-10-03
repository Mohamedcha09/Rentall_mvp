# app/routes_favorites.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Item, Favorite


# -------------------------
# Helper: احضار المستخدم من السيشن (يرجع None بدل ما يرمي استثناء)
# -------------------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    if not uid:
        return None
    return db.get(User, uid)


# ======================================================
# API: /api/favorites  (إضافة/حذف/جلب معرفات المفضلات)
# ======================================================
api = APIRouter(prefix="/api/favorites", tags=["favorites"])

@api.get("/", response_model=List[int])
def list_favorite_ids(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """يرجع قائمة IDs للعناصر الموجودة في المفضلة للمستخدم الحالي."""
    if not user:
        # للـ fetch في الواجهة
        raise HTTPException(status_code=401, detail="Unauthorized")

    ids = [fav.item_id for fav in db.query(Favorite).filter_by(user_id=user.id).all()]
    return ids


@api.post("/{item_id}")
def add_favorite(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """أضف عنصراً إلى المفضلة."""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    exists = db.query(Favorite).filter_by(user_id=user.id, item_id=item_id).first()
    if exists:
        return {"ok": True, "msg": "already"}

    db.add(Favorite(user_id=user.id, item_id=item_id))
    db.commit()
    return {"ok": True}


@api.delete("/{item_id}")
def remove_favorite(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """احذف عنصراً من المفضلة."""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    fav = db.query(Favorite).filter_by(user_id=user.id, item_id=item_id).first()
    if not fav:
        raise HTTPException(status_code=404, detail="Not in favorites")

    db.delete(fav)
    db.commit()
    return {"ok": True}


# ============================================
# صفحة: /favorites  (تعرض عناصر المستخدم المفضلة)
# ============================================
page = APIRouter(tags=["favorites"])

@page.get("/favorites")
def favorites_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    صفحة واجهة تُظهر كل العناصر المفضلة للمستخدم الحالي.
    إذا لم يكن مسجّلاً، نعيده لصفحة الدخول.
    """
    if not user:
        return RedirectResponse(url="/login?next=/favorites", status_code=303)

    favs = (
        db.query(Favorite)
        .filter(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
        .all()
    )
    items = []
    for f in favs:
        it = db.get(Item, f.item_id)
        if it:
            items.append(it)

    return request.app.templates.TemplateResponse(
        "favorites.html",
        {
            "request": request,
            "title": "مفضّلتي",
            "session_user": request.session.get("user"),
            "items": items,
        },
    )


# ==========
# Router واحد
# ==========
router = APIRouter()
router.include_router(api)
router.include_router(page)