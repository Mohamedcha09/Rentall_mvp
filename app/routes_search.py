# app/routes_search.py

from collections import defaultdict
from functools import lru_cache
import re
import unicodedata

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from .catalog_taxonomy import CATEGORY_TREE, canonical_rental_category, taxonomy_label
from .database import get_db
from .models import User, Item
from .rental_catalog import RENTAL_CATEGORY_ALIASES

router = APIRouter()

# Earth radius constant
EARTH_RADIUS_KM = 6371.0


def _taxonomy_key(value: str) -> str:
    """Normalize a taxonomy label for exact multilingual alias lookup."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    text = text.replace("ـ", "")
    text = re.sub("[أإآٱ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[^\w.+×x-]+", " ", text.casefold(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _category_stored_values(value: str) -> tuple[str, ...]:
    """Keep search compatible with declared legacy category spellings."""
    canonical = canonical_rental_category(value)
    values = [str(canonical or "").strip()]
    values.extend(
        alias
        for alias, target in RENTAL_CATEGORY_ALIASES.items()
        if target == canonical
    )
    return tuple(dict.fromkeys(value for value in values if value))


@lru_cache(maxsize=1)
def _taxonomy_alias_index() -> dict[str, tuple[str, ...]]:
    """Map each central EN/FR/AR taxonomy label to stored canonical values.

    The index is static application taxonomy data and contains no listing or
    user data.  It lets general search resolve a translated category/type or
    service name without copying category-specific conditionals into a route.
    Dynamic lookup-table additions remain searchable by their stored names.
    """
    index: dict[str, set[str]] = defaultdict(set)

    def register(value: str, *, category: bool = False, aliases: tuple[str, ...] = ()) -> None:
        canonical = canonical_rental_category(value) if category else str(value or "").strip()
        if not canonical:
            return
        stored_values = _category_stored_values(canonical) if category else (canonical,)
        labels = (
            canonical,
            taxonomy_label(canonical, "fr"),
            taxonomy_label(canonical, "ar"),
            *aliases,
        )
        for label in labels:
            key = _taxonomy_key(label)
            if key:
                index[key].update(stored_values)

    for category, subcategories in CATEGORY_TREE.items():
        category_aliases = tuple(
            alias
            for alias, target in RENTAL_CATEGORY_ALIASES.items()
            if target == canonical_rental_category(category)
        )
        register(category, category=True, aliases=category_aliases)
        for subcategory, third_levels in subcategories.items():
            register(subcategory)
            for third_level in third_levels:
                register(third_level)
    return {key: tuple(sorted(values, key=str.casefold)) for key, values in index.items()}


def _taxonomy_search_values(query: str) -> tuple[str, ...]:
    """Return canonical/legacy values only for an exact known taxonomy alias."""
    return _taxonomy_alias_index().get(_taxonomy_key(query), ())


def _item_search_predicate(query: str):
    """Build one approved-listing text predicate with taxonomy aliases.

    The original free-text matching remains intact.  Exact values derived
    from the central catalog add translated/legacy taxonomy matching only;
    arbitrary user text never becomes a taxonomy filter.
    """
    pattern = f"%{query}%"
    fields = (
        Item.title,
        Item.description,
        Item.category,
        Item.subcategory,
        Item.third_level,
        Item.custom_third_level,
    )
    clauses = [field.ilike(pattern) for field in fields]
    for value in _taxonomy_search_values(query):
        clauses.extend(func.lower(field) == value.casefold() for field in fields)
    return or_(*clauses)

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
            _item_search_predicate(q),
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
                _item_search_predicate(q),
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
        request=request,
        name="search.html",
        context={
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
