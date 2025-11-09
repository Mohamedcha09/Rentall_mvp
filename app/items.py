# app/items.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
import os, secrets, shutil
import unicodedata

# Cloudinary (upload images to the cloud)
import cloudinary
import cloudinary.uploader

from .database import get_db
from .models import Item, User, ItemReview, Favorite as _Fav
from .utils import CATEGORIES, category_label
from .utils_badges import get_user_badges

router = APIRouter()

# Root of the local uploads folder (also mounted in main.py at /uploads)
UPLOADS_ROOT = os.environ.get(
    "UPLOADS_DIR",
    os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "uploads")
)
ITEMS_DIR = os.path.join(UPLOADS_ROOT, "items")
os.makedirs(ITEMS_DIR, exist_ok=True)


# ---------------- Utilities ----------------
def _strip_accents(s: str) -> str:
    if not s:
        return ""
    # يحوّل Montréal -> Montreal
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _haversine_expr(lat1, lon1, lat2, lon2):
    """
    SQL expression for great-circle distance (km).
    6371 = Earth radius in km.
    """
    return 6371 * 2 * func.asin(
        func.sqrt(
            func.pow(func.sin(func.radians(lat2 - lat1) / 2), 2) +
            func.cos(func.radians(lat1)) *
            func.cos(func.radians(lat2)) *
            func.pow(func.sin(func.radians(lon2 - lon1) / 2), 2)
        )
    )


# ---------------- Similar items helpers ----------------
def get_similar_items(db: Session, item: Item):
    """
    يرجّع عناصر مشابهة (نفس الفئة + قرب جغرافي ≤ 50 كم إن توفر lat/lng،
    وإلا فمطابقة المدينة نصياً بعد إزالة التشكيل). يحقن avg_stars و rating_count
    داخل كل عنصر ليقرأها القالب مباشرة.
    """
    limit = 10

    # ---------- تجميعة التقييمات ----------
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
            Item.category == item.category,
            Item.id != item.id,
        )
    )

    results = []
    picked_ids = set()

    # 1) قرب جغرافي (≤ 50 كم) إن توفّر lat/lng
    if item.latitude is not None and item.longitude is not None:
        dist_expr = _haversine_expr(
            float(item.latitude),
            float(item.longitude),
            Item.latitude,
            Item.longitude,
        ).label("distance_km")

        nearby_rows = (
            base_q
            .add_columns(dist_expr)
            .filter(Item.latitude.isnot(None), Item.longitude.isnot(None))
            .filter(dist_expr <= 50)   # ← بدلاً من HAVING
            .order_by(func.random())
            .limit(limit)
            .all()
        )

        for it, avg_stars, rating_count, distance_km in nearby_rows:
            if it.id in picked_ids:
                continue
            it.avg_stars    = float(avg_stars) if avg_stars is not None else None
            it.rating_count = int(rating_count or 0)
            it.distance_km  = float(distance_km) if distance_km is not None else None
            results.append(it)
            picked_ids.add(it.id)

    # 2) نفس المدينة نصياً (بعد إزالة التشكيل) لملء الباقي
    if len(results) < limit and item.city:
        remain = limit - len(results)
        short = (item.city or "").split(",")[0].strip()
        short_norm = _strip_accents(short).lower()

        city_rows = (
            base_q
            .filter(
                or_(
                    func.lower(Item.city).like(f"%{short.lower()}%"),
                    func.lower(Item.city).like(f"%{short_norm}%"),
                )
            )
            .order_by(func.random())
            .limit(remain * 2)  # هامش صغير للازدواجيات
            .all()
        )

        for row in city_rows:
            # مخرجات هذه الاستعلام بدون عمود المسافة: (Item, avg_stars, rating_count)
            it, avg_stars, rating_count = row
            if it.id in picked_ids:
                continue
            it.avg_stars    = float(avg_stars) if avg_stars is not None else None
            it.rating_count = int(rating_count or 0)
            results.append(it)
            picked_ids.add(it.id)
            if len(results) >= limit:
                break

    return results[:limit]


# ---------------- Helpers ----------------
def require_approved(request: Request):
    u = request.session.get("user")
    return u and u.get("status") == "approved"


def is_account_limited(request: Request) -> bool:
    u = request.session.get("user")
    if not u:
        return False
    return u.get("status") != "approved"


def _ext_ok(filename: str) -> bool:
    if not filename:
        return False
    ext = os.path.splitext(filename.lower())[1]
    return ext in [".jpg", ".jpeg", ".png", ".webp"]


def _local_public_url(fname: str) -> str:
    # URL accessible via StaticFiles('/uploads' -> UPLOADS_ROOT)
    return f"/uploads/items/{fname}"


# ================= Items list =================
@router.get("/items")
def items_list(
    request: Request,
    db: Session = Depends(get_db),
    category: str = None,
    sort: str = None,               # sort=random|new
    city: str = None,               # "Paris, France"
    lat: float | None = None,
    lng: float | None = None,
):
    q = db.query(Item).filter(Item.is_active == "yes")
    current_category = None
    if category:
        q = q.filter(Item.category == category)
        current_category = category

    # Filter by city (name-based only)
    applied_name_filter = False
    if city:
        short = (city or "").split(",")[0].strip()
        if short:
            q = q.filter(
                or_(
                    func.lower(Item.city).like(f"%{short.lower()}%"),
                    func.lower(Item.city).like(f"%{(city or '').lower()}%")
                )
            )
            applied_name_filter = True

    # Sort by distance if coordinates were provided
    applied_distance_sort = False
    if lat is not None and lng is not None:
        dist2 = (
            (Item.latitude - float(lat)) * (Item.latitude - float(lat))
            + (Item.longitude - float(lng)) * (Item.longitude - float(lng))
        ).label("dist2")
        q = q.order_by(dist2.asc())
        applied_distance_sort = True

    # Otherwise use sort=new|random
    s = (sort or request.query_params.get("sort") or "random").lower()
    current_sort = s
    if not applied_distance_sort:
        if s == "new":
            q = q.order_by(Item.created_at.desc())
        else:
            q = q.order_by(func.random())

    items = q.all()

    # Prepare view data
    for it in items:
        it.category_label = category_label(it.category)
        it.owner_badges = get_user_badges(it.owner, db) if it.owner else []

    return request.app.templates.TemplateResponse(
        "items.html",
        {
            "request": request,
            "title": "Items",
            "items": items,
            "categories": CATEGORIES,
            "current_category": current_category,
            "session_user": request.session.get("user"),
            "account_limited": is_account_limited(request),
            "current_sort": current_sort,
            "selected_city": city or "",
            "lat": lat,
            "lng": lng,
        }
    )


# ================= Item details =================
@router.get("/items/{item_id}")
def item_detail(request: Request, item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).get(item_id)
    if not item:
        # ⚠️ اسم القالب الصحيح: item_detail.html (بدون s)
        return request.app.templates.TemplateResponse(
            "items_detail.html",
            {
                "request": request,
                "item": None,
                "session_user": request.session.get("user"),
                "immersive": True,
            }
        )

    from sqlalchemy import func as _func

    item.category_label = category_label(item.category)
    owner = db.query(User).get(item.owner_id)
    owner_badges = get_user_badges(owner, db) if owner else []

    # Reviews
    reviews_q = (
        db.query(ItemReview)
        .filter(ItemReview.item_id == item.id)
        .order_by(ItemReview.created_at.desc())
    )
    reviews = reviews_q.all()
    avg_stars = (
        db.query(_func.coalesce(_func.avg(ItemReview.stars), 0))
        .filter(ItemReview.item_id == item.id)
        .scalar() or 0
    )
    cnt_stars = (
        db.query(_func.count(ItemReview.id))
        .filter(ItemReview.item_id == item.id)
        .scalar() or 0
    )

    # Favorite state
    session_u = request.session.get("user")
    is_favorite = False
    if session_u:
        is_favorite = db.query(_Fav.id).filter_by(
            user_id=session_u["id"], item_id=item.id
        ).first() is not None

    # ✅ Bring similar items
    similar_items = get_similar_items(db, item)
    # أعطِ كل عنصر label للإظهار في القالب
    for s in similar_items:
        s.category_label = category_label(s.category)

    return request.app.templates.TemplateResponse(
        "items_detail.html",
        {
            "request": request,
            "item": item,
            "owner": owner,
            "owner_badges": owner_badges,
            "session_user": request.session.get("user"),
            "item_reviews": reviews,
            "item_rating_avg": round(float(avg_stars), 2),
            "item_rating_count": int(cnt_stars),
            "immersive": True,
            "is_favorite": is_favorite,
            # ✅ pass to template
            "similar_items": similar_items,
        }
    )


# ================= Owner's items =================
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

    return request.app.templates.TemplateResponse(
        "owner_items.html",
        {
            "request": request,
            "title": "My Items",
            "items": items,
            "session_user": u,
            "account_limited": is_account_limited(request),
        }
    )


# ================= Add a new item =================
@router.get("/owner/items/new")
def item_new_get(request: Request):
    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    return request.app.templates.TemplateResponse(
        "items_new.html",
        {
            "request": request,
            "title": "Add Item",
            "categories": CATEGORIES,
            "session_user": request.session.get("user"),
            "account_limited": is_account_limited(request),
        }
    )


@router.post("/owner/items/new")
def item_new_post(
    request: Request,
    db: Session = Depends(get_db),
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    city: str = Form(""),
    price_per_day: int = Form(0),
    image: UploadFile = File(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
):
    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    u = request.session.get("user")

    # final path to store in DB (Cloudinary URL or local path /uploads/..)
    image_path_for_db = None

    if image and image.filename:
        if _ext_ok(image.filename):
            ext = os.path.splitext(image.filename)[1].lower()
            fname = f"{u['id']}_{secrets.token_hex(8)}{ext}"
            fpath = os.path.join(ITEMS_DIR, fname)

            uploaded_url = None
            try:
                up = cloudinary.uploader.upload(
                    image.file,
                    folder=f"items/{u['id']}",
                    public_id=os.path.splitext(fname)[0],
                    resource_type="image",
                )
                uploaded_url = (up or {}).get("secure_url")
            except Exception:
                uploaded_url = None

            if not uploaded_url:
                try:
                    try:
                        image.file.seek(0)
                    except Exception:
                        pass
                    with open(fpath, "wb") as f:
                        shutil.copyfileobj(image.file, f)
                    image_path_for_db = _local_public_url(fname)
                except Exception:
                    image_path_for_db = None
            else:
                image_path_for_db = uploaded_url

            try:
                image.file.close()
            except Exception:
                pass

    it = Item(
        owner_id=u["id"],
        title=title,
        description=description,
        city=city,
        price_per_day=price_per_day,
        image_path=image_path_for_db,
        is_active="yes",
        category=category,
        latitude=latitude,
        longitude=longitude,
    )
    db.add(it)
    db.commit()
    return RedirectResponse(url=f"/items/{it.id}", status_code=303)


# ================= All reviews page =================
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

    avg = db.query(func.coalesce(func.avg(ItemReview.stars), 0)).filter(ItemReview.item_id == item.id).scalar() or 0
    cnt = db.query(func.count(ItemReview.id)).filter(ItemReview.item_id == item.id).scalar() or 0

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
