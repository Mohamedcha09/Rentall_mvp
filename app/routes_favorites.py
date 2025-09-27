# app/routes_favorites.py
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, List

from .database import get_db
from .models import Favorite, Item

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


# ===== Helpers =====
def require_user(request: Request) -> dict:
    """
    يعتمد على الجلسة الموجودة لديك (request.session['user'])
    ويرجع معرّف المستخدم. يرمي 401 لو لم يسجّل الدخول.
    """
    u = request.session.get("user")
    if not u or "id" not in u:
        raise HTTPException(status_code=401, detail="يرجى تسجيل الدخول")
    return u


# ===== Endpoints =====

@router.get("", summary="جلب قائمة المفضّلات كعناصر كاملة")
def list_favorites(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="بحث بعنوان/مدينة العنصر (اختياري)")
):
    u = require_user(request)
    qset = (
        db.query(Item)
        .join(Favorite, Favorite.item_id == Item.id)
        .filter(Favorite.user_id == u["id"])
        .filter(Item.is_active == "yes")
        .order_by(Favorite.created_at.desc())
    )

    if q:
        like = f"%{q}%"
        qset = qset.filter((Item.title.ilike(like)) | (Item.city.ilike(like)))

    items = qset.offset(offset).limit(limit).all()

    # إخراج خفيف ومرتب
    data = [
        {
            "id": it.id,
            "title": it.title,
            "city": it.city,
            "price_per_day": it.price_per_day,
            "category": it.category,
            "image_path": it.image_path,
        }
        for it in items
    ]
    return {"items": data, "count": len(data)}


@router.get("/ids", summary="إرجاع فقط معرفات العناصر في المفضّلة")
def list_favorite_ids(
    request: Request,
    db: Session = Depends(get_db),
):
    u = require_user(request)
    rows = (
        db.query(Favorite.item_id)
        .filter(Favorite.user_id == u["id"])
        .order_by(Favorite.created_at.desc())
        .all()
    )
    ids: List[int] = [r[0] for r in rows]
    return {"item_ids": ids}


@router.get("/{item_id}", summary="هل هذا العنصر في المفضّلة؟")
def is_favorite(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    u = require_user(request)
    exists = (
        db.query(Favorite)
        .filter(Favorite.user_id == u["id"], Favorite.item_id == item_id)
        .first()
        is not None
    )
    return {"item_id": item_id, "favorite": exists}


@router.post("/{item_id}", summary="إضافة عنصر إلى المفضّلة")
def add_favorite(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    u = require_user(request)

    item = db.query(Item).filter(Item.id == item_id, Item.is_active == "yes").first()
    if not item:
        raise HTTPException(status_code=404, detail="العنصر غير موجود أو غير متاح")

    fav = db.query(Favorite).filter(
        Favorite.user_id == u["id"], Favorite.item_id == item_id
    ).first()
    if fav:
        # idempotent
        return {"ok": True, "favorite": True}

    try:
        fav = Favorite(user_id=u["id"], item_id=item_id)
        db.add(fav)
        db.commit()
    except IntegrityError:
        db.rollback()
        # في حال UniqueConstraint ضرب بسبب تسابق
        return {"ok": True, "favorite": True}

    return {"ok": True, "favorite": True}


@router.delete("/{item_id}", summary="إزالة عنصر من المفضّلة")
def remove_favorite(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    u = require_user(request)

    fav = db.query(Favorite).filter(
        Favorite.user_id == u["id"], Favorite.item_id == item_id
    ).first()
    if not fav:
        # idempotent
        return {"ok": True, "favorite": False}

    db.delete(fav)
    db.commit()
    return {"ok": True, "favorite": False}