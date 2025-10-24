# app/routes_search.py
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from .database import get_db
from .models import User, Item

router = APIRouter()

# ✅ ثابت: نصف قطر الأرض (لـ Haversine)
EARTH_RADIUS_KM = 6371.0


def _clean_name(first: str, last: str, uid: int) -> str:
    """
    يبني الاسم الكامل بشكل سليم حتى لو كان أحد الحقلين فاضي.
    """
    f = (first or "").strip()
    l = (last or "").strip()
    if f and l:
        full = f"{f} {l}"
    else:
        full = f or l
    return full or f"User {uid}"


# ✅ دالة فلترة ذكية للمدينة أو GPS (أولوية GPS)
def _apply_city_or_gps_filter(qs, city: str | None, lat: float | None, lng: float | None, radius_km: float | None):
    """
    يطبّق فلترة حسب GPS (إن وجد) أو حسب المدينة.
    """
    if lat is not None and lng is not None and radius_km:
        # مسافة Haversine: تعطي المسافة بين نقطتين على الكرة الأرضية
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
        # فلترة بسيطة بالمدينة (غير حساسة لحالة الأحرف)
        qs = qs.filter(Item.city.ilike(f"%{city.strip()}%"))
    return qs


# ✅ API: بحث سريع (يُستخدم في الاقتراحات)
@router.get("/api/search")
def api_search(
    q: str = "",
    city: str | None = Query(None),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    lon: float | None = Query(None),          # ✅ جديد: قبول lon أيضًا من الـURL
    radius_km: float | None = Query(25.0),
    db: Session = Depends(get_db),
):
    """
    بحث حيّ (autocomplete) يدعم الفلترة بالمدينة أو GPS.
    """
    # ✅ لو جاء lon بدون lng ننسخه
    if lng is None and lon is not None:
        lng = lon

    q = (q or "").strip()
    if len(q) < 2:
        return {"users": [], "items": []}

    pattern = f"%{q}%"

    # المستخدمون
    users_rows = (
        db.query(User.id, User.first_name, User.last_name)
        .filter(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
            )
        )
        .limit(8)
        .all()
    )

    users = [
        {
            "id": uid,
            "name": _clean_name(first, last, uid),
            "url": f"/users/{uid}",
        }
        for (uid, first, last) in users_rows
    ]

    # العناصر
    items_q = (
        db.query(Item.id, Item.title, Item.city)
        .filter(
            Item.is_active == "yes",
            or_(
                Item.title.ilike(pattern),
                Item.description.ilike(pattern),
            ),
        )
    )

    items_q = _apply_city_or_gps_filter(items_q, city, lat, lng, radius_km)
    items_rows = items_q.limit(8).all()

    items = [
        {
            "id": iid,
            "title": (title or "").strip(),
            "city": (city or "").strip(),
            "url": f"/items/{iid}",
        }
        for (iid, title, city) in items_rows
    ]

    return {"users": users, "items": items}


# ✅ صفحة نتائج البحث الكاملة
@router.get("/search")
def search_page(
    request: Request,
    q: str = "",
    city: str | None = Query(None),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    lon: float | None = Query(None),          # ✅ جديد: قبول lon أيضًا
    radius_km: float | None = Query(25.0),
    db: Session = Depends(get_db)
):
    """
    صفحة نتائج البحث الرئيسية (تُعرض فيها كل النتائج).
    تدعم الفلترة بالمدينة أو GPS تمامًا مثل الـ API.
    """
    # ✅ ضمّن lon في lng لو كانت lng مفقودة
    if lng is None and lon is not None:
        lng = lon

    q = (q or "").strip()
    users = []
    items = []

    # ✅ قراءة القيم من الكوكي إذا لم تُرسل في الـURL (الاسمين lng/lon)
    try:
        if not city:
            city = request.cookies.get("city")

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
            radius_km = float(ck) if ck else 25.0
    except Exception:
        pass

    if len(q) >= 2:
        pattern = f"%{q}%"

        # المستخدمون
        users_rows = (
            db.query(User.id, User.first_name, User.last_name, User.avatar_path)
            .filter(
                or_(
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                )
            )
            .limit(24)
            .all()
        )
        users = [
            {
                "id": uid,
                "name": _clean_name(first, last, uid),
                "avatar_path": (avatar or "").strip(),
                "url": f"/users/{uid}",
            }
            for (uid, first, last, avatar) in users_rows
        ]

        # العناصر
        items_q = (
            db.query(Item.id, Item.title, Item.city, Item.image_path)
            .filter(
                Item.is_active == "yes",
                or_(
                    Item.title.ilike(pattern),
                    Item.description.ilike(pattern),
                ),
            )
        )

        items_q = _apply_city_or_gps_filter(items_q, city, lat, lng, radius_km)
        items_rows = items_q.limit(24).all()

        items = [
            {
                "id": iid,
                "title": (title or "").strip(),
                "city": (city or "").strip(),
                "image_path": (img or "").strip(),
                "url": f"/items/{iid}",
            }
            for (iid, title, city, img) in items_rows
        ]

    # ✅ إرجاع الصفحة
    return request.app.templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "title": "نتائج البحث",
            "q": q,
            "users": users,
            "items": items,
            "session_user": request.session.get("user"),
            "selected_city": city or "",
            "lat": lat,
            "lng": lng,               # ✅ تأكد من تمرير lng بعد الدمج
            "radius_km": radius_km
        },
    )