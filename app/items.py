# app/items.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
import os, secrets, shutil
import unicodedata
from datetime import date
from typing import Optional

# Cloudinary (upload images to the cloud)
import cloudinary
import cloudinary.uploader

from .database import get_db
from .models import Item, User, ItemReview, Favorite as _Fav
from .utils import CATEGORIES, category_label
from .utils_badges import get_user_badges
from .models import Category, Subcategory

router = APIRouter()

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

        # today's rate
        row = (
            db.query(FxRate)
            .filter(
                FxRate.base == base,
                FxRate.quote == quote,
                FxRate.effective_date == today,
            )
            .first()
        )

        # fallback to last available
        if not row:
            row = (
                db.query(FxRate)
                .filter(FxRate.base == base, FxRate.quote == quote)
                .order_by(FxRate.effective_date.desc())
                .first()
            )

        if row and getattr(row, "rate", None):
            return float(amount) * float(row.rate)

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
):
    # Load DB categories
    categories_db = db.query(Category).order_by(Category.name.asc()).all()

    # =======================
    # LOAD SUBCATEGORIES CORRECTLY
    # =======================
    subcategories_db = []
    if category:
        # 1) Get the category row by name
        cat_obj = db.query(Category).filter(Category.name == category).first()

        # 2) If exists → load its subcategories by category_id
        if cat_obj:
            subcategories_db = (
                db.query(Subcategory)
                .filter(Subcategory.category_id == cat_obj.id)
                .order_by(Subcategory.name.asc())
                .all()
            )

    q = db.query(Item).filter(Item.is_active == "yes",Item.status == "approved")

    current_category = category

    # Filter by category (by name)
    if category:
        q = q.filter(Item.category == category)

        # Filter by subcategory
        sub = request.query_params.get("sub")
        if sub:
            q = q.filter(Item.subcategory == sub)

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
            q = q.order_by(func.random())

    # Fetch items
    items = q.all()

    # Rating
    for it in items:
        avg = db.query(func.avg(ItemReview.stars)).filter(ItemReview.item_id == it.id).scalar()
        cnt = db.query(func.count(ItemReview.id)).filter(ItemReview.item_id == it.id).scalar()
        it.avg_stars = float(avg) if avg else None
        it.rating_count = int(cnt or 0)

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
        items_view.append({
            "item": it,
            "display_price": float(disp_price),
            "display_currency": disp_cur,
        })

    return request.app.templates.TemplateResponse(
        "items.html",
        {
            "request": request,
            "title": "Items",
            "items": items,
            "items_view": items_view,
            "categories": categories_db,
            "current_category": current_category,
            "subcategories": subcategories_db,
            "current_sub": request.query_params.get("sub"),
            "display_currency": disp_cur,
            "selected_city": city or "",
            "current_sort": current_sort,
            "lat": lat,
            "lng": lng,
            "session_user": request.session.get("user"),

        }
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
    owner = db.query(User).get(item.owner_id)
    owner_badges = get_user_badges(owner, db) if owner else []

    # Reviews
    reviews = (
        db.query(ItemReview)
        .filter(ItemReview.item_id == item.id)
        .order_by(ItemReview.created_at.desc())
        .all()
    )

    avg_stars = (
        db.query(_func.coalesce(_func.avg(ItemReview.stars), 0))
        .filter(ItemReview.item_id == item.id)
        .scalar()
        or 0
    )

    cnt_stars = (
        db.query(_func.count(ItemReview.id))
        .filter(ItemReview.item_id == item.id)
        .scalar()
        or 0
    )

    # Favorite
    is_favorite = False
    if session_u:
        is_favorite = (
            db.query(_Fav.id)
            .filter_by(user_id=session_u["id"], item_id=item.id)
            .first()
            is not None
        )

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

    favorite_ids = []
    if session_u:
        favorite_ids = [
            r[0]
            for r in db.query(_Fav.item_id)
                      .filter(_Fav.user_id == session_u["id"])
                      .all()
        ]

    return request.app.templates.TemplateResponse(
        "items_detail.html",
        {
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

    items = (
        db.query(Item)
        .filter(Item.owner_id == u["id"])
        .order_by(Item.created_at.desc())
        .all()
    )

    for it in items:
        it.category_label = category_label(it.category)
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
        "owner_items.html",
        {
            "request": request,
            "title": "My Items",
            "items": items,
            "items_view": owner_items_view,
            "display_currency": disp_cur,
            "session_user": u,
            "account_limited": is_account_limited(request),
        }
    )

@router.get("/owner/items/{item_id}/edit")
def item_edit_get(request: Request, item_id: int, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    item = db.query(Item).get(item_id)
    if not item or item.owner_id != u["id"]:
        return RedirectResponse(url="/owner/items", status_code=303)

    categories = db.query(Category).order_by(Category.name.asc()).all()
    subcategories = (
        db.query(Subcategory)
        .filter(Subcategory.category_id == db.query(Category.id)
        .filter(Category.name == item.category))
        .all()
    )

    return request.app.templates.TemplateResponse(
        "items_edit.html",
        {
            "request": request,
            "item": item,
            "categories": categories,
            "subcategories": subcategories,
            "session_user": u,
        }
    )


@router.post("/owner/items/{item_id}/edit")
def item_edit_post(
    request: Request, item_id: int, db: Session = Depends(get_db),
    title: str = Form(...),
    category: str = Form(...),
    subcategory_id: int = Form(None),
    description: str = Form(""),
    city: str = Form(""),
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

    # Update main fields
    it.title = title
    it.category = category
    it.description = description
    it.city = city

    # Price
    try:
        it.price_per_day = float(price)
        it.price = float(price)
    except:
        it.price = 0

    it.currency = currency
    it.latitude = latitude or None
    it.longitude = longitude or None

    # Subcategory
    sub_name = None
    if subcategory_id:
        sc = db.query(Subcategory).filter(Subcategory.id == subcategory_id).first()
        if sc:
            sub_name = sc.name
    it.subcategory = sub_name

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

    db.commit()

    return RedirectResponse(url="/owner/items", status_code=303)


# ============================================================
# ======================= ADD ITEM ============================
# ============================================================
@router.get("/owner/items/new")
def item_new_get(request: Request, db: Session = Depends(get_db)):
    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    # Load categories from DB
    categories_db = db.query(Category).order_by(Category.name.asc()).all()

    # Load all subcategories once
    subcats_db = db.query(Subcategory).all()

    # Build dictionary: { category_id: [subcat, subcat, ...] }
    subcats_map = {}
    for s in subcats_db:
        subcats_map.setdefault(s.category_id, [])
        subcats_map[s.category_id].append({"id": s.id, "name": s.name})

    return request.app.templates.TemplateResponse(
        "items_new.html",
        {
            "request": request,
            "title": "Add Item",
            "categories": categories_db,     # full category objects
            "subcats_map": subcats_map,     # dict for JS dynamic
            "session_user": request.session.get("user"),
            "account_limited": is_account_limited(request),
        }
    )
@router.post("/owner/items/new")
def item_new_post(
    request: Request,
    db: Session = Depends(get_db),

    # Form fields
    subcategory_id: int | None = Form(None),
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    city: str = Form(""),

    price: str = Form("0"),
    currency: str = Form("CAD"),

    images: list[UploadFile] = File(...),

    latitude: str = Form(""),
    longitude: str = Form(""),
):

    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    u = request.session.get("user")

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

    # ------------------------------
    # GET SUBCATEGORY NAME FROM ID
    # ------------------------------
    subcat_name = None
    if subcategory_id:
        subcat = db.query(Subcategory).filter(Subcategory.id == subcategory_id).first()
        if subcat:
            subcat_name = subcat.name   # "Vans" for example

    # ------------------------------
    # MULTI IMAGES UPLOAD HANDLING
    # ------------------------------
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
        category=category,          # example: Vehicles
        subcategory=subcat_name,    # example: "Vans" instead of id (VERY IMPORTANT)
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
        "items_reviews.html",
        {
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

    # Reset review status
    it.status = "pending"
    it.admin_feedback = None
    it.reviewed_at = None

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
        "item_submitted.html",
        {
            "request": request,
            "session_user": u,
            "item": it,
        }
    )
