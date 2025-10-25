# app/items.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import os, secrets, shutil

# Cloudinary (رفع الصور إلى السحابة)
import cloudinary
import cloudinary.uploader

from .database import get_db
from .models import Item, User
from .utils import CATEGORIES, category_label
from .utils_badges import get_user_badges

router = APIRouter()

# جذر مجلد الرفع المحلي (مُعلن أيضاً في main.py بالـ /uploads)
UPLOADS_ROOT = os.environ.get(
    "UPLOADS_DIR",
    os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "uploads")
)
ITEMS_DIR = os.path.join(UPLOADS_ROOT, "items")
os.makedirs(ITEMS_DIR, exist_ok=True)

# --- Helpers ---
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
    # عنوان يمكن فتحه عبر StaticFiles('/uploads' -> UPLOADS_ROOT)
    return f"/uploads/items/{fname}"

# ================= قائمة العناصر =================
@router.get("/items", response_class=HTMLResponse)
def items_list(
    request: Request,
    db: Session = Depends(get_db),
    category: Optional[str] = None,
    sort: Optional[str] = None,   # random | new
    city: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
):
    # الأساس: عناصر مفعّلة فقط
    q = db.query(Item).filter(Item.is_active == "yes")
    current_category = None

    # فلترة التصنيف
    if category:
        q = q.filter(Item.category == category)
        current_category = category

    # فلترة المدينة (عند عدم وجود إحداثيات)
    if city and (lat is None or lng is None):
        # فلترة بسيطة بالاسم (تعمل مع أي DB)
        q = q.filter(Item.city.ilike(f"%{city}%"))

    # الفرز
    # - عند وجود lat/lng: نفرز بالقرب أولاً (وأيضًا نفلتر العناصر التي فيها إحداثيات)
    # - عند عدم وجودهما: نطبّق sort المعتاد (random/new)
    applied_distance_sort = False
    if lat is not None and lng is not None:
        # مسافة مبسّطة (مربّع الفرق) تعمل على Postgres و SQLite بدون دوال مثل acos
        # distance^2 = (lat - item.lat)^2 + (lng - item.lng)^2
        # مع تجاهل العناصر التي لا تملك إحداثيات
        q = q.filter(Item.latitude.isnot(None), Item.longitude.isnot(None))
        dist2 = (
            (Item.latitude - float(lat)) * (Item.latitude - float(lat))
            + (Item.longitude - float(lng)) * (Item.longitude - float(lng))
        ).label("dist2")
        q = q.order_by(dist2.asc())
        applied_distance_sort = True

    # إن لم نطبّق فرز المسافة، نتبع sort
    s = (sort or request.query_params.get("sort") or "random").lower()
    current_sort = s
    if not applied_distance_sort:
        if s == "new":
            q = q.order_by(Item.created_at.desc())
        else:
            q = q.order_by(func.random())

    items = q.all()

    # تحضير حقول العرض
    for it in items:
        it.category_label = category_label(it.category)
        it.owner_badges = get_user_badges(it.owner, db) if it.owner else []

    return request.app.templates.TemplateResponse(
        "items.html",
        {
            "request": request,
            "title": "العناصر",
            "items": items,
            "categories": CATEGORIES,
            "current_category": current_category,
            "current_sort": current_sort,
            "selected_city": city or "",
            "lat": lat,
            "lng": lng,
            "session_user": request.session.get("user"),
            "account_limited": is_account_limited(request),
        }
    )

# ================= تفاصيل عنصر =================
@router.get("/items/{item_id}", response_class=HTMLResponse)
def item_detail(request: Request, item_id: int, db: Session = Depends(get_db)):
    # استبدال Query.get القديم
    item = db.get(Item, item_id)
    if not item:
        return request.app.templates.TemplateResponse(
            "items_detail.html",
            {"request": request, "item": None, "session_user": request.session.get("user")}
        )

    item.category_label = category_label(item.category)
    owner = db.get(User, item.owner_id)
    owner_badges = get_user_badges(owner, db) if owner else []

    return request.app.templates.TemplateResponse(
        "items_detail.html",
        {
            "request": request,
            "item": item,
            "owner": owner,
            "owner_badges": owner_badges,
            "session_user": request.session.get("user"),
        }
    )

# ================= عناصر المالك =================
@router.get("/owner/items", response_class=HTMLResponse)
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
            "title": "أشيائي",
            "items": items,
            "session_user": u,
            "account_limited": is_account_limited(request),
        }
    )

# ================= إضافة عنصر جديد =================
@router.get("/owner/items/new", response_class=HTMLResponse)
def item_new_get(request: Request):
    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    return request.app.templates.TemplateResponse(
        "items_new.html",
        {
            "request": request,
            "title": "إضافة عنصر",
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
    latitude: float | None = Form(None),   # نخزّن الإحداثيات إن وُجدت
    longitude: float | None = Form(None),
):
    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    u = request.session.get("user")

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