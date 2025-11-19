# app/routes_home.py
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pathlib import Path
from urllib.parse import quote
import random

from .database import get_db
from .models import Item, FxRate
from .utils import CATEGORIES, category_label as _category_label

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


def _serialize(i: Item) -> dict:
    return {
        "id": getattr(i, "id", None),
        "title": getattr(i, "title", "") or "",
        "image_path": getattr(i, "image_path", None) or "/static/placeholder.jpg",
        "city": getattr(i, "city", "") or "",
        "category": getattr(i, "category", "") or "",
        "price_per_day": getattr(i, "price_per_day", None),
        "rating": getattr(i, "rating", 4.8) or 4.8,
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

    if lng is None and lon is not None:
        lng = lon

    try:
        if not city:
            city = request.cookies.get("city") or None

        if lat is None:
            c_lat = request.cookies.get("lat")
            if c_lat:
                lat = float(c_lat)

        if lng is None:
            c_lng = request.cookies.get("lng") or request.cookies.get("lon")
            if c_lng:
                lng = float(c_lng)

        if not radius_km:
            ck = request.cookies.get("radius_km")
            if ck:
                radius_km = float(ck)
    except Exception:
        pass

    session_user = getattr(request, "session", {}).get("user")
    if session_user and session_user.get("display_currency"):
        user_currency = session_user["display_currency"]
    else:
        user_currency = request.cookies.get("disp_cur") or "CAD"

    # NEW: currency symbols
    symbols = {"CAD": "$", "USD": "$", "EUR": "€"}

    rates = load_fx_dict(db)

    base_q = db.query(Item).filter(Item.is_active == "yes")
    filtered_q = _apply_city_or_gps_filter(base_q, city, lat, lng, radius_km)
    filtering = (lat is not None and lng is not None and radius_km) or (city not in (None, ""))

    # ---- Nearby ----
    if filtering:
        nearby_rows = filtered_q.order_by(Item.created_at.desc()).limit(20).all()
    else:
        nearby_rows = base_q.order_by(func.random()).limit(20).all()

    nearby_items = [_serialize(i) for i in nearby_rows]

    for it in nearby_items:
        base = it["currency"]
        price = it.get("price_per_day") or 0
        it["display_price"] = fx_convert(price, base, user_currency, rates)
        it["display_currency"] = user_currency
        it["display_symbol"] = symbols.get(user_currency, user_currency)   # FIX ✔

    # ---- Categories ----
    items_by_category = {}
    for cat in CATEGORIES:
        code = cat.get("key", "")
        label = cat.get("label", "")

        q = base_q
        if filtering:
            q = _apply_city_or_gps_filter(q, city, lat, lng, radius_km)
        q = _apply_category_filter(q, code, label)

        rows = q.order_by(func.random()).limit(12).all()
        lst = [_serialize(i) for i in rows]

        for it in lst:
            base = it["currency"]
            price = it.get("price_per_day") or 0
            it["display_price"] = fx_convert(price, base, user_currency, rates)
            it["display_currency"] = user_currency
            it["display_symbol"] = symbols.get(user_currency, user_currency)   # FIX ✔

        if lst:
            items_by_category[code] = lst

    # ---- All items ----
    if filtering:
        all_rows = filtered_q.order_by(Item.created_at.desc()).limit(60).all()
    else:
        all_rows = base_q.order_by(func.random()).limit(60).all()

    all_items = [_serialize(i) for i in all_rows]

    for it in all_items:
        base = it["currency"]
        price = it.get("price_per_day") or 0
        it["display_price"] = fx_convert(price, base, user_currency, rates)
        it["display_currency"] = user_currency
        it["display_symbol"] = symbols.get(user_currency, user_currency)   # FIX ✔

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
        "radius_km": radius_km or 25.0,
        "category_label": _category_label,
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
