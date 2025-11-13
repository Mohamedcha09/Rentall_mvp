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

router = APIRouter()

# ---------- Uploads config ----------
UPLOADS_ROOT = os.environ.get(
    "UPLOADS_DIR",
    os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "uploads")
)
ITEMS_DIR = os.path.join(UPLOADS_ROOT, "items")
os.makedirs(ITEMS_DIR, exist_ok=True)


# ================= Currency helpers (NEW) =================
def _display_currency(request: Request) -> str:
    """
    تستخرج عملة العرض من middleware (إن وُجدت) وإلا ترجع CAD.
    """
    try:
        cur = getattr(request.state, "display_currency", None)
        if not cur:
            return "CAD"
        return str(cur).upper()
    except Exception:
        return "CAD"


def fx_convert_smart(db: Session, amount: Optional[float], base: str, quote: str) -> float:
    """
    تحويل آمن باستخدام جدول FxRate.
    يأخذ سعر اليوم، وإن لم يوجد → أحدث تاريخ متاح.
    """
    try:
        if amount is None:
            return 0.0
        base = (base or "CAD").upper()
        quote = (quote or "CAD").upper()
        if base == quote:
            return float(amount)

        from .models import FxRate  # الموديل اللي عندك

        today = date.today()

        # جرّب سعر اليوم
        row = (
            db.query(FxRate)
            .filter(
                FxRate.base == base,
                FxRate.quote == quote,
                FxRate.effective_date == today,
            )
            .first()
        )

        if not row:
            # خذ أحدث تاريخ متاح
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
        try:
            return float(amount or 0.0)
        except Exception:
            return 0.0


# ================= Utilities =================
def _strip_accents(s: str) -> str:
    """يحذف التشكيل/اللكنات: Montréal -> Montreal"""
    if not s:
        return ""
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

def _to_float_or_none(v):
    """
    يحوّل أي قيمة إلى float أو None بأمان:
    - "" أو None => None
    - "45,5" => 45.5
    - أرقام فعلية تُحوّل مباشرة
    - أي خطأ يرجع None
    """
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if s == "":
            return None
        s = s.replace(",", ".")
        return float(s)
    except Exception:
        return None

def _to_int_or_default(v, default=0):
    try:
        if v is None:
            return int(default)
        s = str(v).strip()
        if s == "":
            return int(default)
        return int(float(s.replace(",", ".")))
    except Exception:
        return int(default)


# ================= Similar items helpers =================
def get_similar_items(db: Session, item: Item):
    """
    يرجّع عناصر مشابهة (نفس الفئة + قرب جغرافي ≤ 50 كم إن توفر lat/lng،
    وإلا فمطابقة المدينة نصياً بعد إزالة التشكيل). يحقن avg_stars و rating_count
    داخل كل عنصر ليقرأها القالب مباشرة.
    """
    limit = 10

    # تجميعة التقييمات
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
            .filter(dist_expr <= 50)
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
            .limit(remain * 2)  # هامش للازدواجيات
            .all()
        )

        for row in city_rows:
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


# ================= Small helpers =================
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

    # ===== NEW: build items_view with converted display prices =====
    disp_cur = _display_currency(request)
    items_view = []
    for it in items:
        # سعر التخزين يبقى بعملة المنشور item.currency
        # العرض فقط يتحوّل إلى disp_cur
        try:
            base_cur = (it.currency or "CAD").upper()
        except Exception:
            base_cur = "CAD"
        disp_price = fx_convert_smart(db, getattr(it, "price", getattr(it, "price_per_day", 0.0)), base_cur, disp_cur)
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
            "items": items,                 # يبقى كما هو (توافقاً مع قوالبك الحالية)
            "items_view": items_view,       # الجديد: قائمة مع الأسعار المحوّلة
            "display_currency": disp_cur,   # مفيدة لو أردت استخدامها في القالب
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

@router.get("/items/{item_id}")
def item_detail(request: Request, item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).get(item_id)

    # READ display currency EXACTLY LIKE HOME
    session_u = request.session.get("user")
    disp_cur = None
    if session_u and session_u.get("display_currency"):
        disp_cur = session_u["display_currency"].upper()
    else:
        disp_cur = getattr(request.state, "display_currency", "CAD").upper()

    # Inject in request.state (important for money filter)
    request.state.display_currency = disp_cur

    if not item:
        return request.app.templates.TemplateResponse(
            "items_detail.html",
            {
                "request": request,
                "item": None,
                "session_user": session_u,
                "immersive": True,
                "display_currency": disp_cur,
            }
        )

    from sqlalchemy import func as _func

    # category + owner
    item.category_label = category_label(item.category)
    owner = db.query(User).get(item.owner_id)
    owner_badges = get_user_badges(owner, db) if owner else []

    # ---------- Reviews ----------
    reviews = (
        db.query(ItemReview)
        .filter(ItemReview.item_id == item.id)
        .order_by(ItemReview.created_at.desc())
        .all()
    )
    avg_stars = db.query(_func.coalesce(_func.avg(ItemReview.stars), 0)).filter(ItemReview.item_id == item.id).scalar() or 0
    cnt_stars = db.query(_func.count(ItemReview.id)).filter(ItemReview.item_id == item.id).scalar() or 0

    # ---------- Favorite ----------
    is_favorite = False
    if session_u:
        is_favorite = db.query(_Fav.id).filter_by(
            user_id=session_u["id"],
            item_id=item.id
        ).first() is not None

    # ---------- Similar items ----------
    similar_items = get_similar_items(db, item)
    for s in similar_items:
        s.category_label = category_label(s.category)
        base_s = (s.currency or "CAD").upper()
        src_s = getattr(s, "price_per_day", None) or getattr(s, "price", 0)
        s.display_price = fx_convert_smart(db, src_s, base_s, disp_cur)
        s.display_currency = disp_cur

    favorite_ids = []
    if session_u:
        favorite_ids = [
            r[0] for r in db.query(_Fav.item_id).filter(_Fav.user_id == session_u["id"]).all()
        ]

    # ---------- PRICE of main item ----------
    base_cur = (item.currency or "CAD").upper()
    src_amount = getattr(item, "price_per_day", None) or getattr(item, "price", 0)
    display_price = fx_convert_smart(db, src_amount, base_cur, disp_cur)

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

            "display_price": float(display_price),
            "display_currency": disp_cur,
            "base_amount": float(src_amount),
            "base_currency": base_cur,
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

    # (اختياري) يمكن تمرير عرض الأسعار هنا أيضاً إن رغبت:
    disp_cur = _display_currency(request)
    owner_items_view = []
    for it in items:
        base_cur = (getattr(it, "currency", None) or "CAD").upper()
        src_amount = getattr(it, "price", getattr(it, "price_per_day", 0.0))
        owner_items_view.append({
            "item": it,
            "display_price": fx_convert_smart(db, src_amount, base_cur, disp_cur),
            "display_currency": disp_cur,
        })

    return request.app.templates.TemplateResponse(
        "owner_items.html",
        {
            "request": request,
            "title": "My Items",
            "items": items,                     # توافقي
            "items_view": owner_items_view,     # محوّل
            "display_currency": disp_cur,
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

    # ← أسماء الحقول مطابقة للنموذج
    price: str = Form("0"),
    currency: str = Form("CAD"),
    image: UploadFile = File(None),

    # ← مطابقة للنموذج (latitude / longitude)
    latitude: str = Form(""),
    longitude: str = Form(""),
):
    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    u = request.session.get("user")

    # تحويلات آمنة
    lat = _to_float_or_none(latitude)
    lng = _to_float_or_none(longitude)

    # سعر عشري
    try:
        _price = float(str(price).replace(",", ".").strip() or "0")
        if _price < 0:
            _price = 0.0
    except Exception:
        _price = 0.0

    # تحقّق العملة
    currency = (currency or "CAD").upper().strip()
    if currency not in {"CAD", "USD", "EUR"}:
        currency = "CAD"

    # معالجة الصورة (كما هو عندك)
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
                    try: image.file.seek(0)
                    except Exception: pass
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

    # إنشاء السجل
    it = Item(
        owner_id=u["id"],
        title=title,
        description=description,
        city=city,
        category=category,
        is_active="yes",
        latitude=lat,
        longitude=lng,

        # الجديد/الموحّد:
        currency=currency,
        price=_price,
        price_per_day=_price,   # لتوافق القوالب الحالية
        image_path=image_path_for_db,
    )
    db.add(it)
    db.commit()
    try:
        db.refresh(it)
    except Exception:
        pass
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
