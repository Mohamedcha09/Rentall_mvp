# app/routes_search.py

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from .database import get_db
from .models import User, Item

router = APIRouter()

# Earth radius constant
EARTH_RADIUS_KM = 6371.0

def _clean_name(first: str, last: str, uid: int) -> str:
    f = (first or "").strip()
    l = (last or "").strip()
    if f and l:
        return f"{f} {l}"
    return f or l or f"User {uid}"

def _to_float(v, default=None):
    if v is None:
        return default
    try:
        s = str(v).strip()
        if s == "":
            return default
        return float(s)
    except:
        return default

# City/GPS combined filter
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


# ============================================================
# API SEARCH (Live autocomplete)
# ============================================================
@router.get("/api/search")
def api_search(
    q: str = "",
    city: str | None = Query(None),
    lat: str | None = Query(None),
    lng: str | None = Query(None),
    lon: str | None = Query(None),
    radius_km: str | None = Query(None),
    db: Session = Depends(get_db),
):
    if (lng is None or str(lng).strip() == "") and lon not in (None, ""):
        lng = lon

    lat_f = _to_float(lat)
    lng_f = _to_float(lng)
    radius_f = _to_float(radius_km, default=25.0)

    q = (q or "").strip()
    if len(q) < 2:
        return {"users": [], "items": []}

    pattern = f"%{q}%"

    # USERS
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
        {"id": uid, "name": _clean_name(first, last, uid), "url": f"/users/{uid}"}
        for (uid, first, last) in users_rows
    ]

    # ITEMS — FIX: approved only
    items_q = (
        db.query(Item.id, Item.title, Item.city)
        .filter(
            Item.is_active == "yes",
            Item.status == "approved",        # ✔ FIX
            or_(Item.title.ilike(pattern), Item.description.ilike(pattern)),
        )
    )

    items_q = _apply_city_or_gps_filter(items_q, city, lat_f, lng_f, radius_f)
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


# ============================================================
# FULL SEARCH PAGE
# ============================================================
@router.get("/search")
def search_page(
    request: Request,
    q: str = "",
    city: str | None = Query(None),
    lat: str | None = Query(None),
    lng: str | None = Query(None),
    lon: str | None = Query(None),
    radius_km: str | None = Query(None),
    db: Session = Depends(get_db)
):
    if (lng is None or str(lng).strip() == "") and lon not in (None, ""):
        lng = lon

    q = (q or "").strip()
    users = []
    items = []

    # Read cookies if no parameters provided
    try:
        if not city:
            city = request.cookies.get("city")

        if lat in (None, ""):
            c_lat = request.cookies.get("lat")
            if c_lat not in (None, ""):
                lat = c_lat

        if lng in (None, ""):
            c_lng = request.cookies.get("lng") or request.cookies.get("lon")
            if c_lng not in (None, ""):
                lng = c_lng

        if radius_km in (None, ""):
            ck = request.cookies.get("radius_km")
            radius_km = ck if ck else None
    except:
        pass

    lat_f = _to_float(lat)
    lng_f = _to_float(lng)
    radius_f = _to_float(radius_km, default=25.0)

    if len(q) >= 2:
        pattern = f"%{q}%"

        # USERS
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

        # ITEMS — FIX: approved only
        items_q = (
            db.query(Item.id, Item.title, Item.city, Item.image_path)
            .filter(
                Item.is_active == "yes",
                Item.status == "approved",      # ✔ FIX
                or_(Item.title.ilike(pattern), Item.description.ilike(pattern)),
            )
        )

        items_q = _apply_city_or_gps_filter(items_q, city, lat_f, lng_f, radius_f)
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

    return request.app.templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "title": "Search Results",
            "q": q,
            "users": users,
            "items": items,
            "session_user": request.session.get("user"),
            "selected_city": city or "",
            "lat": lat_f,
            "lng": lng_f,
            "radius_km": radius_f
        },
    )
