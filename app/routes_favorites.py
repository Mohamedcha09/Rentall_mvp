# app/api_favorites.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from .database import get_db
from .models import User, Item, Favorite, FxRate
from .utils import category_label

# -----------------------------
# Helper: Get current user
# -----------------------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    if not uid:
        return None
    return db.get(User, uid)

# -----------------------------
# Load 24h FX Rates
# -----------------------------
def load_fx_dict(db: Session):
    rows = (
        db.query(FxRate.base, FxRate.quote, FxRate.rate)
        .filter(FxRate.effective_date == func.current_date())
        .all()
    )
    out = {}
    for base, quote, rate in rows:
        out[(base.strip(), quote.strip())] = float(rate)
    return out

def fx_convert(amount: float, base: str, quote: str, fx: dict):
    if base == quote:
        return round(amount, 2)
    key = (base, quote)
    if key not in fx:
        return round(amount, 2)
    return round(amount * fx[key], 2)

# ===========================================================
# API CRUD
# ===========================================================
api = APIRouter(prefix="/api/favorites", tags=["favorites"])

@api.get("/", response_model=List[int])
def list_favorite_ids(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401, "Unauthorized")
    return [
        fav.item_id
        for fav in db.query(Favorite).filter_by(user_id=user.id).all()
    ]

@api.post("/{item_id}")
def add_favorite(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401, "Unauthorized")

    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    exists = db.query(Favorite).filter_by(user_id=user.id, item_id=item_id).first()
    if exists:
        return {"ok": True}

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
    if not user:
        raise HTTPException(401, "Unauthorized")

    fav = db.query(Favorite).filter_by(user_id=user.id, item_id=item_id).first()
    if not fav:
        raise HTTPException(404, "Not in favorites")

    db.delete(fav)
    db.commit()
    return {"ok": True}

# ===========================================================
# PAGE: /favorites
# ===========================================================
page = APIRouter(tags=["favorites"])

@page.get("/favorites")
def favorites_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login?next=/favorites", 303)

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

    # Determine preferred currency
    session_user = request.session.get("user") or {}
    if session_user.get("display_currency"):
        user_cur = session_user["display_currency"]
    else:
        user_cur = request.cookies.get("disp_cur") or "CAD"

    fx = load_fx_dict(db)

    # Build final items
    enriched = []
    for it in items:
        base = it.currency or "CAD"
        price = getattr(it, "price_per_day", None) or getattr(it, "price", 0)

        enriched.append({
            "id": it.id,
            "title": it.title,
            "image_path": it.image_path,
            "city": it.city,
            "category": it.category,

            # FIXED: safe rating field
            "rating": (
                getattr(it, "avg_stars", None)
                or getattr(it, "rating_avg", None)
                or 4.8
            ),

            # Converted price
            "display_price": fx_convert(price, base, user_cur, fx),
            "display_currency": user_cur,
        })

    return request.app.templates.TemplateResponse(
        "favorites.html",
        {
            "request": request,
            "title": "My Favorites",
            "session_user": session_user,
            "items": enriched,
            "category_label": category_label,
        },
    )

# Combine routes
router = APIRouter()
router.include_router(api)
router.include_router(page)
