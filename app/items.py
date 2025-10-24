# app/items.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func  # ✅ لفرز عشوائي
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
@router.get("/items")
def items_list(
    request: Request,
    db: Session = Depends(get_db),
    category: str = None,
    sort: str = None,   # ✅ دعم اختيار الترتيب عبر الاستعلام
):
    q = db.query(Item).filter(Item.is_active == "yes")
    current_category = None
    if category:
        q = q.filter(Item.category == category)
        current_category = category

    # ✅ افتراضيًا ترتيب عشوائي حتى لا يظهر نفس العنصر أولاً كل مرة
    # استخدم ?sort=new لعرض الأحدث أولاً
    sort = (sort or request.query_params.get("sort") or "random").lower()
    if sort == "new":
        q = q.order_by(Item.created_at.desc())
    else:
        q = q.order_by(func.random())

    items = q.all()
    for it in items:
        it.category_label = category_label(it.category)
        # 🟢 شارات المالك
        it.owner_badges = get_user_badges(it.owner, db) if it.owner else []

    return request.app.templates.TemplateResponse(
        "items.html",
        {
            "request": request,
            "title": "العناصر",
            "items": items,
            "categories": CATEGORIES,
            "current_category": current_category,
            "session_user": request.session.get("user"),
            "account_limited": is_account_limited(request),
            "current_sort": sort,  # ✅ لعرض شارة الترتيب في القالب إن أردت
        }
    )

# ================= تفاصيل عنصر =================
@router.get("/items/{item_id}")
def item_detail(request: Request, item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).get(item_id)
    if not item:
        return request.app.templates.TemplateResponse(
            "items_detail.html",
            {"request": request, "item": None, "session_user": request.session.get("user")}
        )

    item.category_label = category_label(item.category)
    owner = db.query(User).get(item.owner_id)
    owner_badges = get_user_badges(owner, db) if owner else []

    return request.app.templates.TemplateResponse(
        "items_detail.html",
        {
            "request": request,
            "item": item,
            "owner": owner,
            "owner_badges": owner_badges,   # ← مهم
            "session_user": request.session.get("user"),
        }
    )

# ================= عناصر المالك =================
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
            "title": "أشيائي",
            "items": items,
            "session_user": u,
            "account_limited": is_account_limited(request),
        }
    )

# ================= إضافة عنصر جديد =================
@router.get("/owner/items/new")
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
    latitude: float | None = Form(None),   # ✅ جديد: نستقبل latitude من النموذج
    longitude: float | None = Form(None),  # ✅ جديد: نستقبل longitude من النموذج
):
    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    u = request.session.get("user")

    # المسار النهائي الذي سنخزنه في DB (Cloudinary URL أو مسار محلي /uploads/..)
    image_path_for_db = None

    if image and image.filename:
        # 1) تأكيد الامتداد
        if not _ext_ok(image.filename):
            # تجاهل الملف غير المدعوم بهدوء (تقدر ترجع خطأ HTTP لو حاب)
            pass
        else:
            # 2) اسم ملف آمن محلي (للـ fallback أو أي حاجة ثانية)
            ext = os.path.splitext(image.filename)[1].lower()
            fname = f"{u['id']}_{secrets.token_hex(8)}{ext}"
            fpath = os.path.join(ITEMS_DIR, fname)

            # 3) نحاول الرفع إلى Cloudinary أولاً
            uploaded_url = None
            try:
                # ارفع الملف مباشرة من الـ stream إلى كلودينري (resource_type=image)
                up = cloudinary.uploader.upload(
                    image.file,               # stream
                    folder=f"items/{u['id']}",
                    public_id=os.path.splitext(fname)[0],
                    resource_type="image",
                )
                uploaded_url = (up or {}).get("secure_url")
            except Exception:
                uploaded_url = None

            # 4) إذا ما نجح كلودينري → نحفظ محلياً وننشئ URL عام عبر /uploads
            if not uploaded_url:
                try:
                    # لازم نرجّع مؤشر الملف للبداية قبل النسخ
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

            # تأكد إغلاق الملف
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
        price_per_day=price_per_day,
        image_path=image_path_for_db,   # قد يكون Cloudinary URL أو /uploads/items/xxx
        is_active="yes",
        category=category,
        latitude=latitude,    # ✅ جديد: نخزّن الإحداثيات إن وُجدت
        longitude=longitude,  # ✅ جديد: نخزّن الإحداثيات إن وُجدت
    )
    db.add(it)
    db.commit()
    return RedirectResponse(url=f"/items/{it.id}", status_code=303)