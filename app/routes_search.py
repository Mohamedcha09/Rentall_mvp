# app/routes_search.py
from fastapi import APIRouter, Depends, Request, Query  # ✅ إضافة Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from .database import get_db
from .models import User, Item

router = APIRouter()

# ✅ إضافة: نصف قطر الأرض بالكيلومتر لاستخدامه مع دالة Haversine
EARTH_RADIUS_KM = 6371.0

def _clean_name(first: str, last: str, uid: int) -> str:
    """
    يبني الاسم الكامل بشكل سليم حتى لو كان أحد الحقلين فاضي.
    (تم إصلاح السهو: كان f-string ينسى first_name عند وجوده)
    """
    f = (first or "").strip()
    l = (last or "").strip()
    if f and l:
        full = f"{f} {l}"
    else:
        full = f or l
    return full or f"User {uid}"

# ✅ إضافة: دالة مساعدة لتطبيق فلترة المدينة أو GPS (أولوية GPS ثم المدينة)
def _apply_city_or_gps_filter(qs, city: str | None, lat: float | None, lng: float | None, radius_km: float | None):
    # أولوية GPS إن توفّر lat/lng + radius_km
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
        qs = qs.filter(Item.city.ilike(city.strip()))
    return qs

@router.get("/api/search")
def api_search(
    q: str = "",
    # ✅ إضافة: بارامترات اختيارية للفلترة المكانية
    city: str | None = Query(None),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    radius_km: float | None = Query(25.0),
    db: Session = Depends(get_db),
):
    """
    بحث حيّ للمحرك (typeahead) — لا يتطلب تسجيل دخول، ولا يقرأ/يعدّل الـ session.
    يرجّع قوائم مبسطة: users + items، كل عنصر فيه url يُستخدم مباشرة في الواجهة.
    ✅ الآن يدعم الفلترة بالمدينة أو GPS (إن قُدمت البارامترات).
    """
    q = (q or "").strip()
    if len(q) < 2:
        return {"users": [], "items": []}

    pattern = f"%{q}%"

    # --- مستخدمون (بالاسم الأول/الأخير)
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

    # --- عناصر (بالعنوان/الوصف) مع شرط التفعيل
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

    # ✅ تطبيق فلترة المدينة/GPS إن وجدت
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

# (اختياري) صفحة نتائج كاملة /search لو كنت تستعملها في الواجهة
@router.get("/search")
def search_page(
    request: Request,
    q: str = "",
    # ✅ إضافة: نفس بارامترات الفلترة للصفحة الكاملة
    city: str | None = Query(None),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    radius_km: float | None = Query(25.0),
    db: Session = Depends(get_db)
):
    q = (q or "").strip()
    users = []
    items = []

    # ✅ محاولة قراءة قيم محفوظة من الكوكي إن لم تُرسل بالـURL
    try:
        if not city:
            city = request.cookies.get("city")
        if lat is None and (request.cookies.get("lat") not in (None, "")):
            lat = float(request.cookies.get("lat"))
        if lng is None and (request.cookies.get("lng") not in (None, "")):
            lng = float(request.cookies.get("lng"))
        if not radius_km:
            ck = request.cookies.get("radius_km")
            radius_km = float(ck) if ck else 25.0
    except Exception:
        pass

    if len(q) >= 2:
        pattern = f"%{q}%"

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

        # ✅ تطبيق فلترة المدينة/GPS إن وجدت
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

    # استخدم القالب الموجود عندك إن رغبت
    return request.app.templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "title": "نتائج البحث",
            "q": q,
            "users": users,
            "items": items,
            "session_user": request.session.get("user"),
            # ✅ تمرير القيم الحالية للواجهة (مفيد لإظهار الشارة/الحالة)
            "selected_city": city or "",
            "lat": lat,
            "lng": lng,
            "radius_km": radius_km
        },
    )