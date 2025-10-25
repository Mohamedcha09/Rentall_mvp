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
    """حوّل صف Item إلى dict آمن للقالب."""
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
    """طبّق فلتر مدينة أو نصف قطر (Haversine/acos تقريبية)."""
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


# فلترة مرنة حسب التصنيف (تدعم key أو label أو مطابقة جزئية قديمة)
def _apply_category_filter(qs, code: str, label: str):
    # لو عندك البيانات مخزنة بالـ key (vehicle) أو بالـ label (مركبات) أو مشتقة منها
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
    # مجلد static داخل app/
    return Path(__file__).resolve().parent / "static"


def _list_static_images_try(paths: list[str]) -> list[str]:
    """
    يحاول قراءة الصور من عدة مسارات داخل /static.
    يرجّع روابط مثل /static/... مع URL-encoding.
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
    # يدعم: /static/img/banners و /static/banners
    candidates = _list_static_images_try(["img/banners", "banners"])
    random.shuffle(candidates)
    return candidates[:max_count]


def _pick_topstrip_from_static(limit_per_col: int = 12) -> list[list[str]]:
    # يدعم: /static/img/top_slider | /static/img/topstrip | /static/top_slider | /static/topstrip
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
    # alias للباراميتر
    if lng is None and lon is not None:
        lng = lon

    # قراءة الكوكيز لو الباراميترات ناقصة
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

    # سلايدر "بالقرب منك / شائع"
    if filtering_active:
        nearby_rows = filtered_q.order_by(Item.created_at.desc()).limit(20).all()
    else:
        nearby_rows = base_q.order_by(func.random()).limit(20).all()
    nearby_items = [_serialize(i) for i in nearby_rows]

    # سلايدر لكل تصنيف — (تصحيح مهم: CATEGORIES قائمة قواميس)
    items_by_category: dict[str, list[dict]] = {}
    for cat in CATEGORIES:
        code = cat.get("key", "")
        label = cat.get("label", "")
        if not code and not label:
            continue

        q_cat = base_q
        # طبّق فلترة الموقع إذا موجودة
        if filtering_active:
            q_cat = _apply_city_or_gps_filter(q_cat, city, lat, lng, radius_km)
        # فلترة مرنة على التصنيف
        q_cat = _apply_category_filter(q_cat, code, label)

        rows = q_cat.order_by(func.random()).limit(12).all()
        lst = [_serialize(i) for i in rows]
        if lst:
            items_by_category[code] = lst

    # شبكة "كل العناصر"
    if filtering_active:
        all_rows = filtered_q.order_by(Item.created_at.desc()).limit(60).all()
    else:
        all_rows = base_q.order_by(func.random()).limit(60).all()
    all_items = [_serialize(i) for i in all_rows]

    # الميديا: بانرز و Top-Strip من static
    banners = _pick_banners_from_static(max_count=8)
    top_strip_cols = _pick_topstrip_from_static(limit_per_col=12)

    # fallback لو فاضيين
    if not banners and all(len(c) == 0 for c in top_strip_cols):
        fb_banners, fb_cols = _fallback_media_from_items(db)
        banners = fb_banners or banners
        top_strip_cols = fb_cols or top_strip_cols

    # لو ما لقينا بانرز إطلاقًا، خذ من صور العناصر
    if not banners:
        candidates = nearby_items[:5] or all_items[:5]
        banners = [i["image_path"] for i in candidates if i.get("image_path")]

    ctx = {
        "request": request,
        "title": "الرئيسية",
        "nearby_items": nearby_items,
        "items_by_category": items_by_category,
        "all_items": all_items,
        "banners": banners,
        "top_strip_cols": top_strip_cols,
        "selected_city": city or "",
        "lat": lat,
        "lng": lng,
        "radius_km": radius_km or 25.0,
        "category_label": _category_label,  # متاحة في القالب
        "session_user": getattr(request, "session", {}).get("user") if hasattr(request, "session") else None,
        "favorites_ids": [],
    }

    # استخدم templates المسجّلة على التطبيق لو موجودة
    templates = getattr(request.app, "templates", None)
    if templates:
        try:
            templates.env.globals["category_label"] = _category_label
        except Exception:
            pass
        return templates.TemplateResponse("home.html", ctx)

    # لو ما فيه templates على app، أنشئ واحدة محليًا
    from starlette.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    templates.env.globals["category_label"] = _category_label
    return templates.TemplateResponse("home.html", ctx)