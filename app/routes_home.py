# app/routes_home.py
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from .database import get_db
from .models import Item
from .utils import CATEGORIES, category_label

router = APIRouter()

# نفس الثابت المستعمل في /search
EARTH_RADIUS_KM = 6371.0

def _apply_city_or_gps_filter(qs, city: str | None, lat: float | None, lng: float | None, radius_km: float | None):
    """
    فلترة حسب GPS إن توفّر، وإلا حسب المدينة (case-insensitive).
    """
    from sqlalchemy import func  # محليًا لتجنّب أي لبس
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


@router.get("/")
def home_page(
    request: Request,
    # باراميترات اختيارية تأتي من الهيدر/الـlocbar في home.html
    city: str | None = Query(None),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    lon: float | None = Query(None),              # alias مقبول
    radius_km: float | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    الهوم الآن يحترم ?city/lat/lng/radius_km:
    - لو GPS موجود → يعرض عناصر ضمن نصف القطر.
    - غير ذلك لو city موجودة → يعرض عناصر من نفس المدينة.
    - بدون الاثنين → يعرض خليط عام كما كان.
    كما نقرأ من الكوكي إذا الـURL فاضي (lat/lng/city/radius_km).
    """

    # لو lng مفقودة وجاء lon → انسخه
    if lng is None and lon is not None:
        lng = lon

    # جرّب القراءة من الكوكي إذا الباراميترات ناقصة
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

    # ====== Query أساسي ======
    base_q = db.query(Item).filter(Item.is_active == "yes")

    # عناصر للعرض “بالقرب منك/المدينة” (لو فيه فلترة)
    filtered_q = _apply_city_or_gps_filter(base_q, city, lat, lng, radius_km)
    # نحدد هل تم تطبيق فلترة فعلا
    filtering_active = (lat is not None and lng is not None and radius_km) or (city not in (None, ""))

    # “بالقرب منك / شائع”
    if filtering_active:
        nearby_items = (
            filtered_q
            .order_by(Item.created_at.desc())
            .limit(20)
            .all()
        )
    else:
        # بدون فلترة: اعرض “شائع” عشوائي/أحدث
        nearby_items = (
            base_q
            .order_by(func.random())
            .limit(20)
            .all()
        )

    # تجميع حسب التصنيف (كل قسم 12 عنصر)
    items_by_category = {}
    for code, _label in CATEGORIES:
        q_cat = base_q.filter(Item.category == code)
        if filtering_active:
            q_cat = _apply_city_or_gps_filter(q_cat, city, lat, lng, radius_km)
        items_by_category[code] = q_cat.order_by(func.random()).limit(12).all()

    # شبكة كل العناصر (محدودة لعدد مناسب)
    if filtering_active:
        all_items = filtered_q.order_by(Item.created_at.desc()).limit(60).all()
    else:
        all_items = base_q.order_by(func.random()).limit(60).all()

    # تمرير دوال مساعدة للقالب (مثلما تفعل صفحات أخرى)
    def _cat_label(c): return category_label(c)

    return request.app.templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "title": "الرئيسية",
            # أقسام العرض
            "nearby_items": nearby_items,
            "items_by_category": items_by_category,
            "all_items": all_items,
            # لإعادة الاستعمال داخل القالب/الهيدر
            "selected_city": city or "",
            "lat": lat,
            "lng": lng,
            "radius_km": radius_km or 25.0,
            # احتياطي لو كنت تستعمله في القالب
            "category_label": _cat_label,
            "session_user": request.session.get("user"),
        },
    )
