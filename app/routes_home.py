# app/routes_home.py
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pathlib import Path
import random
from urllib.parse import quote  # ⬅️ مهم لترميز أسماء الملفات

from .database import get_db
from .models import Item
from .utils import CATEGORIES, category_label

router = APIRouter()

EARTH_RADIUS_KM = 6371.0


def _apply_city_or_gps_filter(qs, city: str | None, lat: float | None, lng: float | None, radius_km: float | None):
    from sqlalchemy import func
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


# ========= مصادر الصور من مجلد static =========
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _static_dir(*parts: str) -> Path:
    # هذا الملف: app/routes_home.py → parent = app/
    base_app = Path(__file__).resolve().parent
    return base_app / "static" / Path(*parts)


def _list_static_images(subfolder: str) -> list[str]:
    """
    يرجّع روابط /static/img/<subfolder>/<file> مع URL-encoding لاسم الملف.
    """
    folder = _static_dir("img", subfolder)
    if not folder.exists():
        return []
    items: list[str] = []
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in _IMG_EXTS:
            # نبني المسار تحت /static مع ترميز كل جزء يحتوي مسافات/فواصل
            rel = p.relative_to(_static_dir())  # نسبي إلى app/static
            parts = [quote(part) for part in rel.parts]  # ⬅️ هنا الترميز
            url = "/static/" + "/".join(parts)
            items.append(url)
    return items


def _pick_banners_from_static(max_count: int = 8) -> list[str]:
    imgs = _list_static_images("banners")
    if not imgs:
        return []
    random.shuffle(imgs)
    return imgs[:max_count]


def _pick_topstrip_from_static(limit_per_col: int = 12) -> list[list[str]]:
    imgs = _list_static_images("top_slider")
    cols = [[], [], []]
    if not imgs:
        return cols
    random.shuffle(imgs)
    for i, src in enumerate(imgs[: 3 * limit_per_col]):
        cols[i % 3].append(src)
    return cols


# ========= فولباك من العناصر لو ما فيه صور static =========
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

    # قراءة من الكوكي عند النقص
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

    if filtering_active:
        nearby_items = filtered_q.order_by(Item.created_at.desc()).limit(20).all()
    else:
        nearby_items = base_q.order_by(func.random()).limit(20).all()

    items_by_category = {}
    for code, _label in CATEGORIES:
        q_cat = base_q.filter(Item.category == code)
        if filtering_active:
            q_cat = _apply_city_or_gps_filter(q_cat, city, lat, lng, radius_km)
        items_by_category[code] = q_cat.order_by(func.random()).limit(12).all()

    if filtering_active:
        all_items = filtered_q.order_by(Item.created_at.desc()).limit(60).all()
    else:
        all_items = base_q.order_by(func.random()).limit(60).all()

    # ====== صور الـHero والـTop Strip من مجلد static أولًا ======
    banners = _pick_banners_from_static(max_count=8)
    top_strip_cols = _pick_topstrip_from_static(limit_per_col=12)

    # لو فاضية نرجع لفولباك من صور العناصر
    if not banners and all(len(col) == 0 for col in top_strip_cols):
        fb_banners, fb_cols = _fallback_media_from_items(db)
        if not banners:
            banners = fb_banners
        if all(len(col) == 0 for col in top_strip_cols):
            top_strip_cols = fb_cols

    def _cat_label(c): return category_label(c)

    return request.app.templates.TemplateResponse(
        "home.html",
        {
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
            "category_label": _cat_label,
            "session_user": request.session.get("user"),
        },
    )