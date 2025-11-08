# app/routes_home.py
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pathlib import Path
from urllib.parse import quote
import random

from .database import get_db
from .models import Item
from .utils import CATEGORIES, category_label as _category_label

router = APIRouter()

EARTH_RADIUS_KM = 6371.0
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ==========================
# Helpers: serialization
# ==========================
def _serialize(i: Item) -> dict:
    """Convert an Item row into a template-safe dict."""
    return {
        "id": getattr(i, "id", None),
        "title": getattr(i, "title", "") or "",
        "image_path": getattr(i, "image_path", None) or "/static/placeholder.jpg",
        "city": getattr(i, "city", "") or "",
        "category": getattr(i, "category", "") or "",
        "price_per_day": getattr(i, "price_per_day", None),
        "rating": getattr(i, "rating", 4.8) or 4.8,
    }


# ==========================
# Geo / City filter
# ==========================
def _apply_city_or_gps_filter(qs, city: str | None, lat: float | None, lng: float | None, radius_km: float | None):
    """Apply a city filter or a radius filter (approximate Haversine/acos)."""
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


# Flexible category filtering (supports key or label or legacy partial match)
def _apply_category_filter(qs, code: str, label: str):
    # Whether the data is stored by key (vehicle) or by label (Vehicles) or derived
    return qs.filter(
        or_(
            Item.category == code,
            Item.category == label,
            Item.category.ilike(f"%{code}%"),
            Item.category.ilike(f"%{label}%"),
        )
    )


# ==========================
# Static images helpers
# ==========================
def _static_root() -> Path:
    # static folder inside app/
    return Path(__file__).resolve().parent / "static"


def _list_static_images_try(paths: list[str]) -> list[str]:
    """
    Try to read images from several paths under /static.
    Returns URLs like /static/... with URL-encoding.
    """
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


def _pick_banners_from_static(max_count: int = 8) -> list[str]:
    # Supports: /static/img/banners and /static/banners
    candidates = _list_static_images_try(["img/banners", "banners"])
    random.shuffle(candidates)
    return candidates[:max_count]


def _pick_topstrip_from_static(limit_per_col: int = 12) -> list[list[str]]:
    # Supports: /static/img/top_slider | /static/img/topstrip | /static/top_slider | /static/topstrip
    imgs = _list_static_images_try(["img/top_slider", "img/topstrip", "top_slider", "topstrip"])
    cols = [[], [], []]
    if not imgs:
        return cols
    random.shuffle(imgs)
    for i, src in enumerate(imgs[: 3 * limit_per_col]):
        cols[i % 3].append(src)
    return cols


def _fallback_media_from_items(db: Session, limit: int = 24):
    rows = (
        db.query(Item.image_path)
        .filter(Item.is_active == "yes", Item.image_path.isnot(None), Item.image_path != "")
        .order_by(Item.created_at.desc())
        .limit(limit)
        .all()
    )
    imgs = [r[0] for r in rows if r[0]]
    banners = imgs[:5]
    cols = [[], [], []]
    for i, src in enumerate(imgs[5:]):
        cols[i % 3].append(src)
    return banners, cols


# ==========================
# Route
# ==========================
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
    # alias for the parameter
    if lng is None and lon is not None:
        lng = lon

    # Read cookies if parameters are missing
    try:
        if not city:
            city = request.cookies.get("city") or None
        if lat is None:
            c_lat = request.cookies.get("lat")
            if c_lat not in (None, ""):
                lat = float(c_lat)
        if lng is None:
            c_lng = request.cookies.get("lng") or request.cookies.get("lon")
            if c_lng not in (None, ""):
                lng = float(c_lng)
        if not radius_km:
            ck = request.cookies.get("radius_km")
            radius_km = float(ck) if ck else None
    except Exception:
        pass

    base_q = db.query(Item).filter(Item.is_active == "yes")
    filtered_q = _apply_city_or_gps_filter(base_q, city, lat, lng, radius_km)
    filtering_active = (lat is not None and lng is not None and radius_km) or (city not in (None, ""))

    # Slider “Near you / Popular”
    if filtering_active:
        nearby_rows = filtered_q.order_by(Item.created_at.desc()).limit(20).all()
    else:
        nearby_rows = base_q.order_by(func.random()).limit(20).all()
    nearby_items = [_serialize(i) for i in nearby_rows]

    # Slider for each category — (Important fix: CATEGORIES is a list of dicts)
    items_by_category: dict[str, list[dict]] = {}
    for cat in CATEGORIES:
        code = cat.get("key", "")
        label = cat.get("label", "")
        if not code and not label:
            continue

        q_cat = base_q
        # Apply location filter if present
        if filtering_active:
            q_cat = _apply_city_or_gps_filter(q_cat, city, lat, lng, radius_km)
        # Flexible category filter
        q_cat = _apply_category_filter(q_cat, code, label)

        rows = q_cat.order_by(func.random()).limit(12).all()
        lst = [_serialize(i) for i in rows]
        if lst:
            items_by_category[code] = lst

    # Grid “All items”
    if filtering_active:
        all_rows = filtered_q.order_by(Item.created_at.desc()).limit(60).all()
    else:
        all_rows = base_q.order_by(func.random()).limit(60).all()
    all_items = [_serialize(i) for i in all_rows]

    # Media: banners and top-strip from static
    banners = _pick_banners_from_static(max_count=8)
    top_strip_cols = _pick_topstrip_from_static(limit_per_col=12)

    # Fallback if both are empty
    if not banners and all(len(c) == 0 for c in top_strip_cols):
        fb_banners, fb_cols = _fallback_media_from_items(db)
        banners = fb_banners or banners
        top_strip_cols = fb_cols or top_strip_cols

    # If we found no banners at all, take from item images
    if not banners:
        candidates = nearby_items[:5] or all_items[:5]
        banners = [i["image_path"] for i in candidates if i.get("image_path")]

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
        "category_label": _category_label,  # available in template
        "session_user": getattr(request, "session", {}).get("user") if hasattr(request, "session") else None,
        "favorites_ids": [],
    }

    # Use app-registered templates if available
    templates = getattr(request.app, "templates", None)
    if templates:
        try:
            templates.env.globals["category_label"] = _category_label
        except Exception:
            pass
        return templates.TemplateResponse("home.html", ctx)

    # If the app has no templates attribute, create one locally
    from starlette.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    templates.env.globals["category_label"] = _category_label
    return templates.TemplateResponse("home.html", ctx)
