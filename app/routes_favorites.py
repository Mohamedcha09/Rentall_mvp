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

# ----------------------
# Helper: current user
# ----------------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    if not uid:
        return None
    return db.get(User, uid)

# ----------------------
# Load FX Rates (24h)
# ----------------------
def load_fx_dict(db: Session):
    rows = (
        db.query(FxRate.base, FxRate.quote, FxRate.rate)
        .filter(FxRate.effective_date == func.current_date())
        .all()
    )
    rates = {}
    for base, quote, rate in rows:
        rates[(base.strip(), quote.strip())] = float(rate)
    return rates

def fx_convert(amount: float, base: str, quote: str, rates: dict):
    if base == quote:
        return round(amount, 2)
    key = (base, quote)
    if key not in rates:
        return round(amount, 2)
    return round(amount * rates[key], 2)

# ======================================================
# API CRUD
# ======================================================
api = APIRouter(prefix="/api/favorites", tags=["favorites"])

@api.get("/", response_model=List[int])
def list_favorite_ids(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return [fav.item_id for fav in db.query(Favorite).filter_by(user_id=user.id).all()]

@api.post("/{item_id}")
def add_favorite(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    exists = (
        db.query(Favorite)
        .filter_by(user_id=user.id, item_id=item_id)
        .first()
    )
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
        raise HTTPException(status_code=401, detail="Unauthorized")

    fav = db.query(Favorite).filter_by(user_id=user.id, item_id=item_id).first()
    if not fav:
        raise HTTPException(status_code=404, detail="Not in favorites")

    db.delete(fav)
    db.commit()
    return {"ok": True}

# ======================================================
# Page: /favorites
# ======================================================
page = APIRouter(tags=["favorites"])

@page.get("/favorites")
def favorites_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/login?next=/favorites", status_code=303)

    # Load favorites
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

    # ============================
    # Detect user currency
    # ============================
    session_user = request.session.get("user") or {}
    if session_user.get("display_currency"):
        user_currency = session_user["display_currency"]
    else:
        user_currency = request.cookies.get("disp_cur") or "CAD"

    # ============================
    # Load FX rates
    # ============================
    rates = load_fx_dict(db)

    # ============================
    # Prepare items (convert price)
    # ============================
    enriched_items = []
    for it in items:
        base = it.currency or "CAD"
        price = it.price_per_day or 0

        enriched_items.append({
            "id": it.id,
            "title": it.title,
            "image_path": it.image_path,
            "category": it.category,
            "city": it.city,
            "rating": it.rating or 4.8,
            "display_price": fx_convert(price, base, user_currency, rates),
            "display_currency": user_currency,
            "avg_stars": it.rating or 4.8,
        })

    return request.app.templates.TemplateResponse(
        "favorites.html",
        {
            "request": request,
            "title": "My Favorites",
            "session_user": request.session.get("user"),
            "items": enriched_items,
            "category_label": category_label,
        },
    )

# Combine
router = APIRouter()
router.include_router(api)
router.include_router(page)
