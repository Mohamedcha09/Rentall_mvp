# app/routes_home.py
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pathlib import Path
from urllib.parse import quote
import random

from .database import get_db
from .models import Item, FxRate, ItemReview
from .utils import CATEGORIES, category_label as _category_label
from sqlalchemy.sql import func

router = APIRouter()

EARTH_RADIUS_KM = 6371.0
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ================= FX Loader =================
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


def _serialize(i: Item, ratings: dict) -> dict:
    rid = getattr(i, "id", None)
    r = ratings.get(rid, {"avg": 0, "cnt": 0})
    return {
        "id": rid,
        "title": i.title or "",
        "image_path": i.image_path or "/static/placeholder.jpg",
        "city": i.city or "",
        "category": i.category or "",
        "price_per_day": i.price_per_day,
        "rating_avg": r["avg"],
        "rating_count": r["cnt"],
        "currency": i.currency,
    }


# ================= Filters =================
def _apply_city_filter(qs, city):
    if city:
        return qs.filter(Item.city.ilike(f"%{city.strip()}%"))
    return qs


def _apply_category_filter(qs, code: str, label: str):
    return qs.filter(
        or_(
            Item.category == code,
            Item.category == label,
            Item.category.ilike(f"%{code}%"),
            Item.category.ilike(f"%{label}%"),
        )
    )


# ================= Static loaders =================
def _static_root() -> Path:
    return Path(__file__).resolve().parent / "static"


def _list_static_images_try(paths: list[str]) -> list[str]:
    base = _static_root()
    urls: list[str] = []
    for rel in paths:
        folder = base / rel
        if not folder.exists():
            continue
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in _IMG_EXTS:
                r = p.relative_to(base)
                encoded = "/".join(quote(part) for part in r.parts)
                urls.append("/static/" + encoded)
    return urls


def _pick_banners(max_count=8):
    imgs = _list_static_images_try(["img/banners", "banners"])
    random.shuffle(imgs)
    return imgs[:max_count]


def _pick_topstrip(limit_per_col=12):
    imgs = _list_static_images_try(["img/top_slider", "img/topstrip"])
    cols = [[], [], []]
    if not imgs:
        return cols
    random.shuffle(imgs)
    for i, src in enumerate(imgs[:3 * limit_per_col]):
        cols[i % 3].append(src)
    return cols


# ==== Ratings aggregation ====
def load_ratings_map(db: Session):
    rows = (
        db.query(
            ItemReview.item_id.label("iid"),
            func.avg(ItemReview.stars).label("avg"),
            func.count(ItemReview.id).label("cnt"),
        )
        .group_by(ItemReview.item_id)
        .all()
    )
    m = {}
    for r in rows:
        m[r.iid] = {
            "avg": float(r.avg or 0),
            "cnt": int(r.cnt),
        }
    return m


# ================= Home Route =================
@router.get("/")
def home_page(
    request: Request,
    city: str | None = Query(None),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    lon: float | None = Query(None),
    radius_km: float | None = Query(None),
    db: Session = Depends(get_db),
):

    # -------- Load cookies --------
    try:
        if not city:
            city = request.cookies.get("city") or None
    except:
        pass

    # -------- Currency --------
    session_user = getattr(request, "session", {}).get("user")
    if session_user and session_user.get("display_currency"):
        user_currency = session_user["display_currency"]
    else:
        user_currency = request.cookies.get("disp_cur") or "CAD"

    symbols = {"CAD": "$", "USD": "$", "EUR": "€"}
    rates = load_fx_dict(db)

    # -------- Base Query --------
    base_q = db.query(Item).filter(Item.is_active == "yes")
    ratings_map = load_ratings_map(db)

    # ============================================================================
    #                               🔥 NEARBY
    # ============================================================================
    if city:
        nearby_rows = (
            _apply_city_filter(base_q, city)
            .order_by(func.random())
            .limit(20)
            .all()
        )
        if not nearby_rows:
            nearby_rows = base_q.order_by(func.random()).limit(20).all()
    else:
        nearby_rows = base_q.order_by(func.random()).limit(20).all()

    nearby_items = [_serialize(i, ratings_map) for i in nearby_rows]
    for it in nearby_items:
        it["display_price"] = fx_convert(it["price_per_day"], it["currency"], user_currency, rates)
        it["display_currency"] = user_currency
        it["display_symbol"] = symbols[user_currency]

    # ============================================================================
    #                         🔥 CATEGORY SLIDERS (city → random)
    #                         🔥 10 عناصر فقط — Random دائماً
    # ============================================================================
    items_by_category = {}

    for cat in CATEGORIES:
        code = cat.get("key")
        label = cat.get("label")

        # Try same city
        if city:
            q_city = _apply_category_filter(
                _apply_city_filter(base_q, city),
                code, label
            )
            city_items = q_city.order_by(func.random()).limit(10).all()

            if city_items:
                chosen = city_items
            else:
                chosen = _apply_category_filter(base_q, code, label).order_by(func.random()).limit(10).all()
        else:
            chosen = _apply_category_filter(base_q, code, label).order_by(func.random()).limit(10).all()

        lst = [_serialize(i, ratings_map) for i in chosen]

        # currency convert
        for it in lst:
            it["display_price"] = fx_convert(it["price_per_day"], it["currency"], user_currency, rates)
            it["display_currency"] = user_currency
            it["display_symbol"] = symbols[user_currency]

        items_by_category[code] = lst

    # ============================================================================
    #                           🔥 ALL ITEMS
    # ============================================================================
    all_rows = base_q.order_by(func.random()).limit(20).all()
    all_items = [_serialize(i, ratings_map) for i in all_rows]

    for it in all_items:
        it["display_price"] = fx_convert(it["price_per_day"], it["currency"], user_currency, rates)
        it["display_currency"] = user_currency
        it["display_symbol"] = symbols[user_currency]

    # ============================================================================
    #                           TEMPLATE
    # ============================================================================
    banners = _pick_banners()
    top_strip_cols = _pick_topstrip()

    ctx = {
        "request": request,
        "title": "Home",
        "nearby_items": nearby_items,
        "items_by_category": items_by_category,
        "all_items": all_items,
        "banners": banners,
        "top_strip_cols": top_strip_cols,
        "selected_city": city or "",
        "lat": lat,
        "lng": lng,
        "radius_km": radius_km,
        "category_label": _category_label,
        "session_user": session_user,
        "favorites_ids": [],
    }

    templates = getattr(request.app, "templates")
    templates.env.globals["category_label"] = _category_label
    return templates.TemplateResponse("home.html", ctx)
