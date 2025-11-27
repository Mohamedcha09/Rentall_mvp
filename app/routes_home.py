# app/routes_home.py

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pathlib import Path
from urllib.parse import quote
import random

from .database import get_db
from .models import Item, FxRate, ItemReview, Category
from sqlalchemy.sql import func
from .utils import category_label as _category_label   # ← FIXED ✔ IMPORT

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


# ======================================
# SERIALIZER — FIX: add subcategory ✔
# ======================================
def _serialize(i: Item, ratings: dict) -> dict:
    rid = getattr(i, "id", None)
    r = ratings.get(rid, {"avg": 0, "cnt": 0})
    return {
        "id": rid,
        "title": getattr(i, "title", "") or "",
        "image_path": getattr(i, "image_path", None) or "/static/placeholder.jpg",
        "city": getattr(i, "city", "") or "",
        "category": getattr(i, "category", "") or "",
        "subcategory": getattr(i, "subcategory", "") or "",   # ← ADDED ✔
        "price_per_day": getattr(i, "price_per_day", None),

        "rating_avg": r["avg"],
        "rating_count": r["cnt"],

        "currency": getattr(i, "currency", "CAD"),
    }


# ================= Filters =================
def _apply_city_or_gps_filter(qs, city, lat, lng, radius_km):
    if lat is not None and lng is not None and radius_km:
        distance_expr = EARTH_RADIUS_KM * func.acos(
            func.cos(func.radians(lat)) *
            func.cos(func.radians(Item.latitude)) *
            func.cos(func.radians(Item.longitude) - func.radians(lng)) +
            func.sin(func.radians(lat)) *
            func.sin(func.radians(Item.latitude))
        )
        qs = qs.filter(
            Item.latitude.isnot(None),
            Item.longitude.isnot(None),
            distance_expr <= radius_km
        )
    elif city:
        qs = qs.filter(Item.city.ilike(f"%{city.strip()}%"))
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
    candidates = _list_static_images_try(["img/banners", "banners"])
    random.shuffle(candidates)
    return candidates[:max_count]


def _pick_topstrip(limit_per_col=12):
    imgs = _list_static_images_try(["img/top_slider", "img/topstrip", "top_slider", "topstrip"])
    cols = [[], [], []]
    if not imgs:
        return cols
    random.shuffle(imgs)
    for i, src in enumerate(imgs[: 3 * limit_per_col]):
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
            "avg": float(r.avg) if r.avg is not None else 0.0,
            "cnt": int(r.cnt or 0),
        }
    return m


# ================= HOME PAGE =================
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

    # Fix lon->lng
    if lng is None and lon is not None:
        lng = lon

    # Load cookies
    try:
        if not city:
            city = request.cookies.get("city") or None

        if lat is None and request.cookies.get("lat"):
            lat = float(request.cookies.get("lat"))

        if lng is None:
            ck = request.cookies.get("lng") or request.cookies.get("lon")
            if ck:
                lng = float(ck)

        if not radius_km and request.cookies.get("radius_km"):
            radius_km = float(request.cookies.get("radius_km"))
    except Exception:
        pass

    # Currency
    session_user = getattr(request, "session", {}).get("user")
    if session_user and session_user.get("display_currency"):
        user_currency = session_user["display_currency"]
    else:
        user_currency = request.cookies.get("disp_cur") or "CAD"

    symbols = {"CAD": "$", "USD": "$", "EUR": "€"}

    rates = load_fx_dict(db)

    # Base items
    base_q = db.query(Item).filter(Item.is_active == "yes")
    filtered_q = _apply_city_or_gps_filter(base_q, city, lat, lng, radius_km)
    filtering = (lat and lng and radius_km) or (city not in (None, ""))

    # Nearby items
    if filtering:
        nearby_rows = filtered_q.order_by(Item.created_at.desc()).limit(20).all()
    else:
        nearby_rows = base_q.order_by(func.random()).limit(20).all()

    ratings_map = load_ratings_map(db)
    nearby_items = [_serialize(i, ratings_map) for i in nearby_rows]

    for it in nearby_items:
        base = it["currency"]
        price = it.get("price_per_day") or 0
        it["display_price"] = fx_convert(price, base, user_currency, rates)
        it["display_symbol"] = symbols.get(user_currency, user_currency)

    # ================================
    # LOAD ALL CATEGORIES (FIXED) ✔
    # ================================
    items_by_category = {}
    db_categories = db.query(Category).order_by(Category.id).all()

    for cat in db_categories:
        code = cat.name
        label = cat.name   # same

        q = base_q
        if filtering:
            q = _apply_city_or_gps_filter(q, city, lat, lng, radius_km)

        q = _apply_category_filter(q, code, label)   # FIXED ✔

        rows = q.order_by(Item.created_at.desc()).limit(12).all()

        lst = [_serialize(i, ratings_map) for i in rows]

        for it in lst:
            base = it["currency"]
            price = it.get("price_per_day") or 0
            it["display_price"] = fx_convert(price, base, user_currency, rates)
            it["display_symbol"] = symbols.get(user_currency, user_currency)

        if lst:
            items_by_category[code] = lst

    # ALL ITEMS
    if filtering:
        all_rows = filtered_q.order_by(Item.created_at.desc()).limit(60).all()
    else:
        all_rows = base_q.order_by(func.random()).limit(60).all()

    all_items = [_serialize(i, ratings_map) for i in all_rows]

    for it in all_items:
        base = it["currency"]
        price = it.get("price_per_day") or 0
        it["display_price"] = fx_convert(price, base, user_currency, rates)
        it["display_symbol"] = symbols.get(user_currency, user_currency)

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
        "radius_km": radius_km or 25,
        "category_label": _category_label,     # FIXED ✔
        "session_user": session_user,
        "favorites_ids": [],
    }

    templates = getattr(request.app, "templates", None)
    if templates:
        templates.env.globals["category_label"] = _category_label
        return templates.TemplateResponse("home.html", ctx)

    from starlette.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    templates.env.globals["category_label"] = _category_label
    return templates.TemplateResponse("home.html", ctx)
