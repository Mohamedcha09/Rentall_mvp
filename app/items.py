# app/items.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, or_, and_
from sqlalchemy.exc import SQLAlchemyError
import os, random, secrets, shutil
import unicodedata
from datetime import date
from typing import Optional
from urllib.parse import urlparse

# Cloudinary (upload images to the cloud)
import cloudinary
import cloudinary.uploader

from .database import get_db
from .models import (
    Item,
    User,
    ItemReview,
    Favorite as _Fav,
    Booking,
    FreezeDeposit,
    MessageThread,
    Order,
    Report,
)
from .utils import category_label
from .utils_badges import get_user_badges
from .models import Category, Subcategory
from .catalog_taxonomy import (
    TaxonomyValidationError,
    catalog_tree_payload,
    listing_hierarchy,
    normalize_language,
    resolve_listing_hierarchy,
    taxonomy_label,
    third_levels_for,
)
from .finder_service import remove_listing_index, sync_listing_index

router = APIRouter()

_OWNER_ITEMS_NOTICE_KEY = "owner_items_notice"


def _taxonomy_language(request: Request) -> str:
    """The site already stores its selected language in this cookie."""
    return normalize_language(request.cookies.get("lang"))


def _taxonomy_form_payload(db: Session, request: Request) -> dict:
    categories = db.query(Category).order_by(Category.name.asc()).all()
    subcategories = db.query(Subcategory).order_by(Subcategory.name.asc()).all()
    return catalog_tree_payload(categories, subcategories, _taxonomy_language(request))


def _render_item_new_form(
    request: Request,
    db: Session,
    *,
    form_values: dict | None = None,
    form_error: str | None = None,
    website_error: bool = False,
    status_code: int = 200,
):
    """Render Create Listing from the one persisted taxonomy payload.

    Category and subcategory lookup rows are deliberately not created during a
    GET. The additive migration owns that bootstrap, while this payload is the
    single source used both by the visible selects and their progressive JS.
    """
    taxonomy_payload = _taxonomy_form_payload(db, request)
    return request.app.templates.TemplateResponse(
        request=request,
        name="items_new.html",
        context={
            "request": request,
            "title": "Add Item",
            "taxonomy_payload": taxonomy_payload,
            "taxonomy_language": _taxonomy_language(request),
            "session_user": request.session.get("user"),
            "account_limited": is_account_limited(request),
            "website_error": website_error,
            "form_values": form_values or {},
            "form_error": form_error,
        },
        status_code=status_code,
    )


def _render_item_edit_form(
    request: Request,
    db: Session,
    item: Item,
    *,
    form_values: dict | None = None,
    form_error: str | None = None,
    website_error: bool = False,
    status_code: int = 200,
):
    """Render Edit Listing with the same taxonomy payload as Create Listing."""
    return request.app.templates.TemplateResponse(
        request=request,
        name="items_edit.html",
        context={
            "request": request,
            "item": item,
            "taxonomy_payload": _taxonomy_form_payload(db, request),
            "taxonomy_language": _taxonomy_language(request),
            "session_user": request.session.get("user"),
            "website_error": website_error,
            "form_values": form_values or {},
            "form_error": form_error,
        },
        status_code=status_code,
    )


def _set_owner_items_notice(request: Request, kind: str, text: str) -> None:
    """Store a route-private My Listings notice for the following redirect."""
    request.session[_OWNER_ITEMS_NOTICE_KEY] = {
        "kind": "success" if kind == "success" else "error",
        "text": text,
    }


def _consume_owner_items_notice(request: Request):
    notice = request.session.pop(_OWNER_ITEMS_NOTICE_KEY, None)
    if not isinstance(notice, dict):
        return None

    text = str(notice.get("text") or "").strip()
    if not text:
        return None

    return {
        "kind": "success" if notice.get("kind") == "success" else "error",
        "text": text,
    }


def _owner_listing_delete_blockers(db: Session, item_id: int) -> list[str]:
    """
    Return direct Item dependencies that make an owner hard-delete unsafe.

    The policy intentionally blocks *all* booking history, not only active dates:
    Booking carries payment, payout, deposit, and dispute records.  Blocking the
    remaining direct references prevents implicit cascades from erasing user
    history such as conversations and saved listings.
    """
    dependency_checks = (
        ("bookings", Booking),
        ("orders", Order),
        ("reviews", ItemReview),
        ("reports", Report),
        ("messages", MessageThread),
        ("deposit records", FreezeDeposit),
        ("favorites", _Fav),
    )
    blockers = []
    for label, model in dependency_checks:
        if db.query(model.id).filter(model.item_id == item_id).first() is not None:
            blockers.append(label)
    return blockers

# ---------- Uploads config ----------
UPLOADS_ROOT = os.environ.get(
    "UPLOADS_DIR",
    os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "uploads")
)
ITEMS_DIR = os.path.join(UPLOADS_ROOT, "items")
os.makedirs(ITEMS_DIR, exist_ok=True)


# ================= Currency helpers =================
def _display_currency(request: Request) -> str:
    try:
        allowed_list = getattr(request.app.state, "supported_currencies", ["CAD", "USD", "EUR"])
        allowed = {c.upper() for c in allowed_list}
    except Exception:
        allowed = {"CAD", "USD", "EUR"}

    disp = None

    # session
    try:
        sess = request.session or {}
    except Exception:
        sess = {}

    sess_user = sess.get("user") or {}
    geo_sess = sess.get("geo") or {}

    # 1) user preference
    cur_user = str(sess_user.get("display_currency") or "").upper()
    if cur_user in allowed:
        disp = cur_user

    # 2) geo
    if not disp:
        cur_geo = str(geo_sess.get("currency") or "").upper()
        if cur_geo in allowed:
            disp = cur_geo

    # 3) cookie
    if not disp:
        try:
            cur_cookie = str(request.cookies.get("disp_cur") or "").upper()
        except Exception:
            cur_cookie = ""
        if cur_cookie in allowed:
            disp = cur_cookie

    # 4) default
    if not disp:
        disp = "CAD"

    try:
        request.state.display_currency = disp
    except Exception:
        pass

    return disp


def fx_convert_smart(db: Session, amount: Optional[float], base: str, quote: str) -> float:
    try:
        if amount is None:
            return 0.0
        base = (base or "CAD").upper()
        quote = (quote or "CAD").upper()
        if base == quote:
            return float(amount)

        from .models import FxRate
        today = date.today()

        # A request-scoped Session is shared by the route.  Caching this
        # public daily rate here eliminates repeated identical FxRate queries
        # for each card while keeping all users and requests isolated.
        cache = db.info.setdefault("sevor_fx_rate_cache", {})
        cache_key = (base, quote, today)
        if cache_key not in cache:
            rate = (
                db.query(FxRate.rate)
                .filter(
                    FxRate.base == base,
                    FxRate.quote == quote,
                    FxRate.effective_date == today,
                )
                .scalar()
            )

            # Fallback to the latest available rate only once per pair.
            if rate is None:
                rate = (
                    db.query(FxRate.rate)
                    .filter(FxRate.base == base, FxRate.quote == quote)
                    .order_by(FxRate.effective_date.desc())
                    .limit(1)
                    .scalar()
                )
            cache[cache_key] = float(rate) if rate is not None else None

        rate = cache[cache_key]
        if rate:
            return float(amount) * rate

        return float(amount)
    except Exception:
        return float(amount or 0.0)


# ================= Utilities =================
def _strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _haversine_expr(lat1, lon1, lat2, lon2):
    return 6371 * 2 * func.asin(
        func.sqrt(
            func.pow(func.sin(func.radians(lat2 - lat1) / 2), 2)
            + func.cos(func.radians(lat1))
            * func.cos(func.radians(lat2))
            * func.pow(func.sin(func.radians(lon2 - lon1) / 2), 2)
        )
    )


def _to_float_or_none(v):
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace(",", ".")
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def _to_int_or_default(v, default=0):
    try:
        if v is None:
            return int(default)
        s = str(v).strip().replace(",", ".")
        if s == "":
            return int(default)
        return int(float(s))
    except Exception:
        return int(default)


_WEBSITE_URL_MAX_LENGTH = 2048


def _normalize_website_url(value: str | None) -> str | None:
    """Return a safe HTTP(S) website URL, or None for an empty optional value."""
    raw = (value or "").strip()
    if not raw:
        return None
    if len(raw) > _WEBSITE_URL_MAX_LENGTH:
        raise ValueError("Website URL is too long.")
    if any(char.isspace() for char in raw):
        raise ValueError("Website URL cannot contain whitespace.")

    try:
        initial = urlparse(raw)
    except ValueError as exc:
        raise ValueError("Website URL is invalid.") from exc

    initial_scheme = initial.scheme.lower()
    if raw.startswith("//"):
        raw = f"https:{raw}"
    elif initial_scheme in {"http", "https"}:
        # Keep a supplied HTTP(S) URL; the parsed host is checked below.
        pass
    elif initial_scheme:
        # urlparse reads a bare host with a port (example.com:8080) as a
        # scheme. Treat that specific shape as a bare URL, but reject every
        # actual non-HTTP(S) scheme such as javascript: or data:.
        if "://" not in raw and "." in initial_scheme:
            raw = f"https://{raw}"
        else:
            raise ValueError("Website URL must use HTTP or HTTPS.")
    else:
        raw = f"https://{raw}"

    try:
        parsed = urlparse(raw)
        hostname = parsed.hostname
        parsed.port  # validates malformed ports before the URL is saved
    except ValueError as exc:
        raise ValueError("Website URL is invalid.") from exc

    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        raise ValueError("Website URL must use HTTP or HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Website URL cannot include credentials.")

    normalized = parsed._replace(scheme=parsed.scheme.lower()).geturl()
    if len(normalized) > _WEBSITE_URL_MAX_LENGTH:
        raise ValueError("Website URL is too long.")
    return normalized


# ================= Similar items =================
def get_similar_items(db: Session, item: Item):
    limit = 10

    rev_agg = (
        db.query(
            ItemReview.item_id.label("iid"),
            func.avg(ItemReview.stars).label("avg_stars"),
            func.count(ItemReview.id).label("rating_count"),
        )
        .group_by(ItemReview.item_id)
        .subquery()
    )

    base_q = (
        db.query(
            Item,
            rev_agg.c.avg_stars,
            rev_agg.c.rating_count,
        )
        .options(selectinload(Item.owner))
        .outerjoin(rev_agg, rev_agg.c.iid == Item.id)
        .filter(
            Item.is_active == "yes",
            Item.status == "approved",
            Item.category == item.category,
            Item.id != item.id,
        )
    )

    results = []
    picked_ids = set()

    # 1) Geo
    if item.latitude is not None and item.longitude is not None:
        dist_expr = _haversine_expr(
            float(item.latitude),
            float(item.longitude),
            Item.latitude,
            Item.longitude,
        ).label("distance_km")

        nearby_rows = (
            base_q.add_columns(dist_expr)
            .filter(Item.latitude.isnot(None), Item.longitude.isnot(None))
            .filter(dist_expr <= 50)
            .order_by(func.random())
            .limit(limit)
            .all()
        )

        for it, avg_stars, rating_count, dist_km in nearby_rows:
            if it.id in picked_ids:
                continue
            it.avg_stars = float(avg_stars) if avg_stars else None
            it.rating_count = int(rating_count or 0)
            it.distance_km = float(dist_km) if dist_km else None
            results.append(it)
            picked_ids.add(it.id)

    # 2) City
    if len(results) < limit and item.city:
        remain = limit - len(results)
        short = (item.city or "").split(",")[0].strip()
        short_norm = _strip_accents(short).lower()

        city_rows = (
            base_q.filter(
                or_(
                    func.lower(Item.city).like(f"%{short.lower()}%"),
                    func.lower(Item.city).like(f"%{short_norm}%"),
                )
            )
            .order_by(func.random())
            .limit(remain * 2)
            .all()
        )

        for row in city_rows:
            it, avg_stars, rating_count = row
            if it.id in picked_ids:
                continue
            it.avg_stars = float(avg_stars) if avg_stars else None
            it.rating_count = int(rating_count or 0)
            results.append(it)
            picked_ids.add(it.id)
            if len(results) >= limit:
                break

    return results[:limit]


# ================= Account helpers =================
def require_approved(request: Request):
    u = request.session.get("user")
    return u and u.get("status") == "approved"


def is_account_limited(request: Request) -> bool:
    u = request.session.get("user")
    return bool(u and u.get("status") != "approved")


def _ext_ok(filename: str) -> bool:
    if not filename:
        return False
    ext = os.path.splitext(filename.lower())[1]
    return ext in [".jpg", ".jpeg", ".png", ".webp"]


def _local_public_url(fname: str) -> str:
    return f"/uploads/items/{fname}"

@router.get("/items")
def items_list(
    request: Request,
    db: Session = Depends(get_db),
    category: str = None,
    sort: str = None,
    city: str = None,
    lat: float | None = None,
    lng: float | None = None,
    seller: str = None,
    service: str = None,
):
    # Explore uses the exact persisted lookup source as Create/Edit/POST.
    # The additive taxonomy migration seeds configured categories independently
    # of listing count, so a newly seeded branch remains visible with zero
    # listings without inventing a browse-only category that the form cannot
    # submit or validate.
    categories_db = db.query(Category).order_by(Category.name.asc()).all()
    categories_for_explore = categories_db

    # =======================
    # LOAD SUBCATEGORIES CORRECTLY
    # =======================
    subcategories_db = []
    if category:
        cat_obj = db.query(Category).filter(Category.name == category).first()
        if cat_obj:
            subcategories_db = (
                db.query(Subcategory)
                .filter(Subcategory.category_id == cat_obj.id)
                .order_by(Subcategory.name.asc())
                .all()
            )
    subcategories_for_explore = subcategories_db

    # =======================
    # NEW: seller filter (all | company | individual)
    # =======================
    seller = (seller or request.query_params.get("seller") or "all").lower().strip()
    if seller not in ("all", "company", "individual"):
        seller = "all"

    # Keep the same listing selection while loading the already-rendered owner
    # relation in one batch for the Explore card avatar presentation.
    q = (
        db.query(Item)
        .options(selectinload(Item.owner))
        .filter(Item.is_active == "yes", Item.status == "approved")
    )

    # Apply seller filter (JOIN users)
    if seller != "all":
        q = q.join(Item.owner).filter(func.lower(User.account_type) == seller)

    current_category = category

    # Filter by category (by canonical stored name).  Third-level filtering is
    # optional and is only exposed when the selected category/type has services.
    if category:
        q = q.filter(Item.category == category)

        # Filter by subcategory
        sub = request.query_params.get("sub")
        if sub:
            q = q.filter(Item.subcategory == sub)

            allowed_services = third_levels_for(category, sub)
            selected_service = (service or request.query_params.get("service") or "").strip()
            if selected_service and selected_service in allowed_services:
                q = q.filter(Item.third_level == selected_service)
            elif selected_service:
                # A stale/forged child filter must never silently look active.
                selected_service = ""
        else:
            selected_service = ""
    else:
        sub = ""
        selected_service = ""

    third_levels = [
        {"name": value}
        for value in third_levels_for(category, sub)
    ]

    # City filtering
    if city:
        short = (city or "").split(",")[0].strip()
        if short:
            q = q.filter(
                or_(
                    func.lower(Item.city).like(f"%{short.lower()}%"),
                    func.lower(Item.city).like(f"%{city.lower()}%"),
                )
            )

    # Sort by distance
    applied_distance_sort = False
    if lat is not None and lng is not None:
        dist2 = (
            (Item.latitude - float(lat)) * (Item.latitude - float(lat))
            + (Item.longitude - float(lng)) * (Item.longitude - float(lng))
        ).label("dist2")
        q = q.order_by(dist2.asc())
        applied_distance_sort = True

    # Normal sorting
    s = (sort or request.query_params.get("sort") or "random").lower()
    current_sort = s

    if not applied_distance_sort:
        if s == "new":
            q = q.order_by(Item.created_at.desc())
        else:
            # Preserve a random display order without making the database sort
            # every matching row with RANDOM().
            q = q.order_by(Item.id.desc())

    # Fetch items
    items = q.all()
    if not applied_distance_sort and s != "new":
        random.shuffle(items)

    # Aggregate ratings for all rendered cards in one indexed query instead
    # of issuing an average and count query for every individual item.
    ratings_by_item_id = {}
    item_ids = [item.id for item in items]
    if item_ids:
        rating_rows = (
            db.query(
                ItemReview.item_id,
                func.avg(ItemReview.stars).label("avg_stars"),
                func.count(ItemReview.id).label("rating_count"),
            )
            .filter(ItemReview.item_id.in_(item_ids))
            .group_by(ItemReview.item_id)
            .all()
        )
        ratings_by_item_id = {
            row.item_id: (row.avg_stars, row.rating_count)
            for row in rating_rows
        }

    for item in items:
        avg, count = ratings_by_item_id.get(item.id, (None, 0))
        item.avg_stars = float(avg) if avg else None
        item.rating_count = int(count or 0)

    # Price conversion
    disp_cur = _display_currency(request)
    items_view = []
    for it in items:
        base_cur = (it.currency or "CAD").upper()
        disp_price = fx_convert_smart(
            db,
            getattr(it, "price", getattr(it, "price_per_day", 0)),
            base_cur,
            disp_cur,
        )
        items_view.append(
            {
                "item": it,
                "display_price": float(disp_price),
                "display_currency": disp_cur,
            }
        )

    session_user = request.session.get("user")
    favorite_ids = []
    if session_user and session_user.get("id"):
        favorite_ids = [
            row[0]
            for row in db.query(_Fav.item_id)
            .filter(_Fav.user_id == session_user["id"])
            .all()
        ]

    return request.app.templates.TemplateResponse(
        request=request,
        name="items.html",
        context={
            "request": request,
            "title": "Items",
            "items": items,
            "items_view": items_view,
            "categories": categories_for_explore,
            "current_category": current_category,
            "current_seller": seller,  # ✅ NEW
            "subcategories": subcategories_for_explore,
            "current_sub": sub,
            "third_levels": third_levels,
            "current_service": selected_service,
            "taxonomy_label": taxonomy_label,
            "taxonomy_language": _taxonomy_language(request),
            "display_currency": disp_cur,
            "selected_city": city or "",
            "current_sort": current_sort,
            "lat": lat,
            "lng": lng,
            "session_user": request.session.get("user"),
            "favorite_ids": favorite_ids,
        },
    )


# ============================================================
# ======================= ITEM DETAIL =========================
# ============================================================
@router.get("/items/{item_id}")
def item_detail(request: Request, item_id: int, db: Session = Depends(get_db)):
    # 1) اجلب العنصر من قاعدة البيانات
    item = db.query(Item).get(item_id)
    session_u = request.session.get("user")

    # 2) إذا المنشور غير موجود → رجّع المستخدم لصفحة items
    if not item:
        return RedirectResponse(url="/items", status_code=303)

    # 3) إذا المنشور ليس approved → امنع الكل ماعدا صاحبه
    if item.status != "approved":
        if not session_u or session_u["id"] != item.owner_id:
            return RedirectResponse(url="/items", status_code=303)

    # 4) عملة العرض
    disp_cur = _display_currency(request)

    from sqlalchemy import func as _func

    item.category_label = category_label(item.category)
    item.taxonomy_hierarchy = listing_hierarchy(item, _taxonomy_language(request))
    owner = db.query(User).get(item.owner_id)
    owner_badges = get_user_badges(owner, db) if owner else []

    # Reviews
    reviews = (
        db.query(ItemReview)
        .filter(ItemReview.item_id == item.id)
        .order_by(ItemReview.created_at.desc())
        .all()
    )

    avg_stars, cnt_stars = (
        db.query(
            _func.coalesce(_func.avg(ItemReview.stars), 0),
            _func.count(ItemReview.id),
        )
        .filter(ItemReview.item_id == item.id)
        .one()
    )
    avg_stars = avg_stars or 0
    cnt_stars = cnt_stars or 0

    # Load a signed-in user's favorites once; the same collection feeds both
    # the current-item state and the similar-item cards.
    favorite_ids = []
    if session_u:
        favorite_ids = [
            row[0]
            for row in db.query(_Fav.item_id)
            .filter(_Fav.user_id == session_u["id"])
            .all()
        ]
    is_favorite = item.id in favorite_ids

    # Similar items
    similar_items = get_similar_items(db, item)
    for s in similar_items:
        s.category_label = category_label(s.category)
        base_s = (s.currency or "CAD").upper()
        src_s = getattr(s, "price_per_day", None) or getattr(s, "price", 0)
        s.display_price = fx_convert_smart(db, src_s, base_s, disp_cur)
        s.display_currency = disp_cur

    # Main price
    base_cur = (item.currency or "CAD").upper()
    src_amount = getattr(item, "price_per_day", None) or getattr(item, "price", 0)
    display_price = fx_convert_smart(db, src_amount, base_cur, disp_cur)

    # Do not render a legacy or manually entered unsafe external URL.
    try:
        website_url = _normalize_website_url(getattr(item, "website_url", None))
    except ValueError:
        website_url = None

    return request.app.templates.TemplateResponse(
        request=request,
        name="items_detail.html",
        context={
            "request": request,
            "item": item,
            "owner": owner,
            "owner_badges": owner_badges,
            "session_user": session_u,
            "item_reviews": reviews,
            "item_rating_avg": float(avg_stars),
            "item_rating_count": int(cnt_stars),
            "immersive": True,
            "is_favorite": is_favorite,
            "similar_items": similar_items,
            "favorite_ids": favorite_ids,
            "converted_amount": float(display_price),
            "converted_currency": disp_cur,
            "display_price": float(display_price),
            "display_currency": disp_cur,
            "base_amount": float(src_amount),
            "base_currency": base_cur,
            "website_url": website_url,
            "item_hierarchy": item.taxonomy_hierarchy,
        }
    )


# ============================================================
# ======================= OWNER ITEMS =========================
# ============================================================
@router.get("/owner/items")
def my_items(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    listing_notice = _consume_owner_items_notice(request)

    items = (
        db.query(Item)
        .filter(Item.owner_id == u["id"])
        .order_by(Item.created_at.desc())
        .all()
    )

    for it in items:
        it.category_label = category_label(it.category)
        it.taxonomy_hierarchy = listing_hierarchy(it, _taxonomy_language(request))
        it.taxonomy_display = " · ".join(row["value"] for row in it.taxonomy_hierarchy)
        it.owner_badges = get_user_badges(it.owner, db) if it.owner else []

    disp_cur = _display_currency(request)
    owner_items_view = []

    for it in items:
        base_cur = (getattr(it, "currency", None) or "CAD").upper()
        src_amount = getattr(it, "price", getattr(it, "price_per_day", 0.0))

        owner_items_view.append(
            {
                "item": it,
                "display_price": fx_convert_smart(db, src_amount, base_cur, disp_cur),
                "display_currency": disp_cur,
            }
        )

    return request.app.templates.TemplateResponse(
        request=request,
        name="owner_items.html",
        context={
            "request": request,
            "title": "My Items",
            "items": items,
            "items_view": owner_items_view,
            "display_currency": disp_cur,
            "session_user": u,
            "account_limited": is_account_limited(request),
            "listing_notice": listing_notice,
        }
    )

@router.get("/owner/items/{item_id}/edit")
def item_edit_get(
    request: Request,
    item_id: int,
    website_error: bool = False,
    db: Session = Depends(get_db),
):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    item = db.query(Item).get(item_id)
    if not item or item.owner_id != u["id"]:
        return RedirectResponse(url="/owner/items", status_code=303)

    return _render_item_edit_form(request, db, item, website_error=website_error)


@router.post("/owner/items/{item_id}/edit")
def item_edit_post(
    request: Request, item_id: int, db: Session = Depends(get_db),
    title: str = Form(""),
    category: str = Form(""),
    subcategory_id: str | None = Form(None),
    third_level: str = Form(""),
    custom_third_level: str = Form(""),
    description: str = Form(""),
    city: str = Form(""),
    website_url: str = Form(""),
    no_website: bool = Form(False),
    price: str = Form("0"),
    currency: str = Form("CAD"),
    images: list[UploadFile] = File(None),
    latitude: str = Form(""),
    longitude: str = Form("")
):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    it = db.query(Item).get(item_id)
    if not it or it.owner_id != u["id"]:
        return RedirectResponse(url="/owner/items", status_code=303)

    form_values = {
        "title": title,
        "category": category,
        "subcategory_id": subcategory_id or "",
        "third_level": third_level,
        "custom_third_level": custom_third_level,
        "description": description,
        "city": city,
        "website_url": website_url,
        "no_website": no_website,
        "price": price,
        "currency": currency,
        "latitude": latitude,
        "longitude": longitude,
    }
    if not str(title or "").strip():
        return _render_item_edit_form(
            request, db, it, form_values=form_values,
            form_error="Enter a title for your listing.", status_code=422,
        )

    try:
        normalized_website_url = None if no_website else _normalize_website_url(website_url)
    except ValueError:
        return _render_item_edit_form(
            request, db, it, form_values=form_values,
            form_error="Enter a complete website URL or select that you do not have one.",
            website_error=True, status_code=422,
        )

    try:
        # A pre-expansion listing can legitimately have only two levels.  If
        # its parent path is unchanged, preserve that honest unknown type;
        # new listings and moved paths still require a configured L3 choice.
        legacy_blank_path = None
        if not str(getattr(it, "third_level", "") or "").strip() and not str(
            getattr(it, "custom_third_level", "") or ""
        ).strip():
            legacy_blank_path = (
                str(getattr(it, "category", "") or ""),
                str(getattr(it, "subcategory", "") or "") or None,
            )
        hierarchy = resolve_listing_hierarchy(
            db,
            category_name=category,
            subcategory_id=subcategory_id,
            third_level=third_level,
            custom_third_level=custom_third_level,
            legacy_blank_path=legacy_blank_path,
        )
    except TaxonomyValidationError as exc:
        return _render_item_edit_form(
            request, db, it, form_values=form_values,
            form_error=str(exc), status_code=422,
        )

    # Update main fields
    it.title = title
    it.category = hierarchy["category"]
    it.subcategory = hierarchy["subcategory"]
    it.third_level = hierarchy["third_level"]
    it.custom_third_level = hierarchy["custom_third_level"]
    it.description = description
    it.city = city
    it.website_url = normalized_website_url

    # Price
    try:
        it.price_per_day = float(price)
        it.price = float(price)
    except:
        it.price = 0

    it.currency = currency
    it.latitude = latitude or None
    it.longitude = longitude or None

    # Upload new images (optional)
    if images:
        new_list = []
        for img in images:
            if img and img.filename:
                up = cloudinary.uploader.upload(img.file, folder=f"items/{u['id']}")
                url = (up or {}).get("secure_url")
                if url:
                    new_list.append(url)
        if new_list:
            it.image_urls = new_list
            it.image_path = new_list[0]

    # after edit → back to pending
    it.status = "pending"
    it.admin_feedback = None
    it.reviewed_at = None

    # Finder's document is derived only from public approved listings.  Keep
    # its removal in this same transaction, so a freshly edited pending item
    # cannot remain discoverable through an old search document.
    sync_listing_index(db, it)

    db.commit()

    return RedirectResponse(url="/owner/items", status_code=303)


@router.post("/owner/items/{item_id}/delete")
def owner_item_delete(request: Request, item_id: int, db: Session = Depends(get_db)):
    """Permanently delete an unused owner listing without touching related history."""
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    item = db.query(Item).get(item_id)
    if not item or item.owner_id != u["id"]:
        # Avoid exposing another owner’s listing through this destructive route.
        raise HTTPException(status_code=404, detail="Item not found")

    try:
        blockers = _owner_listing_delete_blockers(db, item.id)
    except SQLAlchemyError:
        # If a dependency cannot be checked, fail closed and preserve the item.
        db.rollback()
        _set_owner_items_notice(
            request,
            "error",
            "This listing can’t be deleted until its related activity can be checked.",
        )
        return RedirectResponse(url="/owner/items", status_code=303)

    if blockers:
        _set_owner_items_notice(
            request,
            "error",
            "This listing can’t be deleted because it has related rental, payment, or activity records.",
        )
        return RedirectResponse(url="/owner/items", status_code=303)

    try:
        remove_listing_index(db, item.id)
        db.delete(item)
        db.commit()
    except SQLAlchemyError:
        # A database-level relation that is not represented above must never be
        # bypassed; roll back and keep the listing intact.
        db.rollback()
        _set_owner_items_notice(
            request,
            "error",
            "This listing can’t be deleted because it has related records.",
        )
        return RedirectResponse(url="/owner/items", status_code=303)

    _set_owner_items_notice(request, "success", "Listing deleted.")
    return RedirectResponse(url="/owner/items", status_code=303)


# ============================================================
# ======================= ADD ITEM ============================
# ============================================================
@router.get("/owner/items/new")
def item_new_get(
    request: Request,
    website_error: bool = False,
    db: Session = Depends(get_db),
):
    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    return _render_item_new_form(request, db, website_error=website_error)
@router.post("/owner/items/new")
def item_new_post(
    request: Request,
    db: Session = Depends(get_db),

    # Form fields
    subcategory_id: str | None = Form(None),
    third_level: str = Form(""),
    custom_third_level: str = Form(""),
    title: str = Form(""),
    category: str = Form(""),
    description: str = Form(""),
    city: str = Form(""),
    website_url: str = Form(""),
    no_website: bool = Form(False),

    price: str = Form("0"),
    currency: str = Form("CAD"),

    images: list[UploadFile] | None = File(None),

    latitude: str = Form(""),
    longitude: str = Form(""),
):

    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    u = request.session.get("user")

    form_values = {
        "title": title,
        "category": category,
        "subcategory_id": subcategory_id or "",
        "third_level": third_level,
        "custom_third_level": custom_third_level,
        "description": description,
        "city": city,
        "website_url": website_url,
        "no_website": no_website,
        "price": price,
        "currency": currency,
        "latitude": latitude,
        "longitude": longitude,
    }
    required_values = (
        (title, "Enter a title for your listing."),
        (category, "Choose a category."),
        (description, "Add a description for your listing."),
        (city, "Choose a city or area."),
    )
    for value, message in required_values:
        if not str(value or "").strip():
            return _render_item_new_form(
                request, db, form_values=form_values,
                form_error=message, status_code=422,
            )

    try:
        normalized_website_url = None if no_website else _normalize_website_url(website_url)
    except ValueError:
        return _render_item_new_form(
            request, db, form_values=form_values,
            form_error="Enter a complete website URL or select that you do not have one.",
            website_error=True, status_code=422,
        )

    lat = _to_float_or_none(latitude)
    lng = _to_float_or_none(longitude)

    # --- PRICE ---
    try:
        _price = float(str(price).replace(",", ".").strip() or "0")
        if _price < 0:
            _price = 0.0
    except Exception:
        _price = 0.0

    # --- CURRENCY ---
    currency = (currency or "CAD").upper().strip()
    if currency not in {"CAD", "USD", "EUR"}:
        currency = "CAD"

    try:
        hierarchy = resolve_listing_hierarchy(
            db,
            category_name=category,
            subcategory_id=subcategory_id,
            third_level=third_level,
            custom_third_level=custom_third_level,
        )
    except TaxonomyValidationError as exc:
        # Do not trust a manually altered form payload.  This validates both
        # child-parent relationships and the configured third-level branch.
        return _render_item_new_form(
            request, db, form_values=form_values,
            form_error=str(exc), status_code=422,
        )

    # ------------------------------
    # MULTI IMAGES UPLOAD HANDLING
    # ------------------------------
    images = images or []
    if not any(image and image.filename and _ext_ok(image.filename) for image in images):
        return _render_item_new_form(
            request,
            db,
            form_values=form_values,
            form_error="Choose at least one JPG, PNG, or WebP image.",
            status_code=422,
        )
    image_urls_list = []
    fallback_image = None  # first image

    for img in images:
        if not img or not img.filename or not _ext_ok(img.filename):
            continue

        ext = os.path.splitext(img.filename)[1].lower()
        fname = f"{u['id']}_{secrets.token_hex(8)}{ext}"
        fpath = os.path.join(ITEMS_DIR, fname)

        uploaded_url = None

        # Upload to Cloudinary
        try:
            up = cloudinary.uploader.upload(
                img.file,
                folder=f"items/{u['id']}",
                public_id=os.path.splitext(fname)[0],
                resource_type="image",
            )
            uploaded_url = (up or {}).get("secure_url")
        except Exception:
            uploaded_url = None

        # Local fallback
        if not uploaded_url:
            try:
                img.file.seek(0)
                with open(fpath, "wb") as f:
                    shutil.copyfileobj(img.file, f)
                uploaded_url = _local_public_url(fname)
            except Exception:
                uploaded_url = None

        # Store
        if uploaded_url:
            image_urls_list.append(uploaded_url)
            if fallback_image is None:
                fallback_image = uploaded_url

        try:
            img.file.close()
        except:
            pass

    # ------------------------------
    # CREATE ITEM
    # ------------------------------
    it = Item(
        owner_id=u["id"],
        title=title,
        description=description,
        city=city,
        website_url=normalized_website_url,
        category=hierarchy["category"],
        subcategory=hierarchy["subcategory"],
        third_level=hierarchy["third_level"],
        custom_third_level=hierarchy["custom_third_level"],
        is_active="yes",
        latitude=lat,
        longitude=lng,
        currency=currency,
        price=_price,
        price_per_day=_price,

        # First image
        image_path=fallback_image,

        # ALL images
        image_urls=image_urls_list or None,
        status="pending"

    )

    db.add(it)
    # New owner listings start pending, so this is a no-op today; keeping the
    # lifecycle hook here makes any future status change explicit and avoids a
    # hidden Finder-only creation path.
    sync_listing_index(db, it)
    db.commit()
    db.refresh(it)

    return RedirectResponse(url=f"/owner/items/{it.id}/submitted",status_code=303)

# ============================================================
# ======================= ALL REVIEWS =========================
# ============================================================
@router.get("/items/{item_id}/reviews")
def item_reviews_all(request: Request, item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).get(item_id)
    if not item:
        return RedirectResponse(url="/items", status_code=303)

    q = (
        db.query(ItemReview)
        .filter(ItemReview.item_id == item.id)
        .order_by(ItemReview.created_at.desc())
    )

    reviews = q.all()

    avg = (
        db.query(func.coalesce(func.avg(ItemReview.stars), 0))
        .filter(ItemReview.item_id == item.id)
        .scalar()
        or 0
    )

    cnt = (
        db.query(func.count(ItemReview.id))
        .filter(ItemReview.item_id == item.id)
        .scalar()
        or 0
    )

    return request.app.templates.TemplateResponse(
        request=request,
        name="items_reviews.html",
        context={
            "request": request,
            "title": f"All reviews • {item.title}",
            "item": item,
            "reviews": reviews,
            "avg": round(float(avg), 2),
            "cnt": int(cnt),
            "session_user": request.session.get("user"),
        }
    )


@router.post("/owner/items/{item_id}/resubmit")
def item_resubmit(request: Request, item_id: int, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    it = db.query(Item).get(item_id)
    if not it or it.owner_id != u["id"]:
        raise HTTPException(404, "Item not found")

    is_admin = str(u.get("role") or "").lower() == "admin"
    if not is_admin and (it.status or "").lower() not in {"rejected", "needs_revision"}:
        _set_owner_items_notice(
            request,
            "error",
            "Only a listing that needs changes can be resubmitted for review.",
        )
        return RedirectResponse(url="/owner/items", status_code=303)

    # Reset review status
    it.status = "pending"
    it.admin_feedback = None
    it.reviewed_at = None
    sync_listing_index(db, it)

    db.commit()

    return RedirectResponse(url="/owner/items", status_code=303)


@router.get("/owner/items/{item_id}/submitted")
def item_submitted(request: Request, item_id: int, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    it = db.query(Item).get(item_id)
    if not it or it.owner_id != u["id"]:
        return RedirectResponse(url="/owner/items", status_code=303)

    return request.app.templates.TemplateResponse(
        request=request,
        name="item_submitted.html",
        context={
            "request": request,
            "session_user": u,
            "item": it,
        }
    )
