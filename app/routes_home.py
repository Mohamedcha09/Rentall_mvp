# app/routes_home.py
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pathlib import Path
import random

from .database import get_db
from .models import Item
from .utils import CATEGORIES, category_label

router = APIRouter()

EARTH_RADIUS_KM = 6371.0

def _apply_city_or_gps_filter(qs, city: str | None, lat: float | None, lng: float | None, radius_km: float | None):
    """
    فلترة حسب GPS إن توفّر، وإلا حسب المدينة (case-insensitive).
    """
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


# ---------- مصادر الصور الثابتة (static) ----------
_VALID_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

def _static_url(request: Request, rel_path: str) -> str:
    """
    يحوّل مسارًا نسبيًا داخل static إلى URL. يفترض أنك عامل mount:
    app.mount('/static', StaticFiles(directory='app/static'), name='static')
    """
    # نتأكد من عدم وجود سلاش أولي مزدوج
    rel_path = rel_path.lstrip("/")
    return f"/static/{rel_path}"

def _collect_static_images(request: Request, subdir: str) -> list[str]:
    """
    يقرأ كل الصور من app/static/<subdir>/ ويرجع URLs.
    """
    # الجذر النسبي من مجلد المشروع
    root = Path(__file__).resolve().parent.parent  # يشير إلى app/
    folder = root / "static" / subdir
    urls: list[str] = []
    try:
        if folder.exists():
            for p in sorted(folder.iterdir()):
                if p.is_file() and p.suffix.lower() in _VALID_EXTS:
                    rel = f"{subdir}/{p.name}"
                    urls.append(_static_url(request, rel))
    except Exception:
        pass
    return urls

def _banners_from_static(request: Request) -> list[str]:
    imgs = _collect_static_images(request, "img/banners")
    random.shuffle(imgs)
    return imgs

def _topstrip_from_static(request: Request) -> list[list[str]]:
    imgs = _collect_static_images(request, "img/top_slider")
    random.shuffle(imgs)
    # وزّعها على 3 أعمدة
    cols = [[], [], []]
    for i, u in enumerate(imgs):
        cols[i % 3].append(u)
    return cols


# ---------- fallback من العناصر في الداتابيز ----------
def _fallback_media_from_items(db: Session, limit: int = 18):
    """
    بدائل في حال مجلدات static فاضية.
    """
    rows = (
        db.query(Item.image_path)
        .filter(Item.is_active == "yes", Item.image_path.isnot(None), Item.image_path != "")
        .order_by(Item.created_at.desc())
        .limit(limit)
        .all()
    )
    imgs = [r[0] for r in rows if r[0]]
    banners = imgs[:3]
    cols = [[], [], []]
    for i, src in enumerate(imgs[3:]):
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
    # دعم lon كبديل
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

    # ---------- HERO + TOP STRIP من static ----------
    banners = _banners_from_static(request)           # من app/static/img/banners/
    top_strip_cols = _topstrip_from_static(request)   # من app/static/img/top_slider/

    # إن كانت مجلدات static فارغة، نلجأ إلى fallback من العناصر حتى لا تختفي الأقسام
    if not banners:
        banners, _fallback_cols = _fallback_media_from_items(db)
        if not any(top_strip_cols):
            top_strip_cols = _fallback_cols

    def _cat_label(c): return category_label(c)

    return request.app.templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "title": "الرئيسية",
            "nearby_items": nearby_items,
            "items_by_category": items_by_category,
            "all_items": all_items,
            # ⬅️ هذه القيم الآن قادمة من مجلدات static التي حددتها
            "banners": banners,
            "top_strip_cols": top_strip_cols,
            # باراميترات الفلترة لواجهة المستخدم
            "selected_city": city or "",
            "lat": lat,
            "lng": lng,
            "radius_km": radius_km or 25.0,
            "category_label": _cat_label,
            "session_user": request.session.get("user"),
        },
    )