# app/items.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, List

# Cloudinary (يقرأ CLOUDINARY_URL تلقائياً إن كانت موجودة)
import cloudinary
import cloudinary.uploader

from fastapi import (
    APIRouter,
    Depends,
    Request,
    HTTPException,
    UploadFile,
    File,
    Form,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Item, User

# دالة تنسيق التصنيفات للقوالب (اختياري)
try:
    from .utils import category_label
except Exception:
    def category_label(c: str) -> str:
        return c

router = APIRouter(tags=["items"])

# ======== إعداد Cloudinary (اختياري لو تحب تفرض secure=True) ========
try:
    cloudinary.config(secure=True)
except Exception:
    pass

# ======== مساعدات ========
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

CATEGORIES = {
    "vehicle": "مركبات / نقل",
    "tools": "معدات وأدوات",
    "electronics": "إلكترونيات",
    "home": "منزل وحديقة",
    "other": "أخرى",
}

def _get_current_user(request: Request, db: Session) -> Optional[User]:
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    return db.get(User, uid) if uid else None

def _ext_lower(name: str) -> str:
    import os
    _, ext = os.path.splitext((name or "").lower())
    return ext

def _validate_basic(
    title: str, description: str, city: str, price_per_day: int, category: str
):
    errs = {}
    if not title or len(title.strip()) < 3:
        errs["title"] = "العنوان قصير جداً."
    if not description or len(description.strip()) < 5:
        errs["description"] = "الوصف قصير جداً."
    if not city:
        errs["city"] = "المدينة مطلوبة."
    try:
        p = int(price_per_day)
        if p <= 0:
            errs["price_per_day"] = "السعر اليومي يجب أن يكون أكبر من صفر."
    except Exception:
        errs["price_per_day"] = "صيغة السعر غير صحيحة."
    if category not in CATEGORIES:
        errs["category"] = "تصنيف غير مدعوم."
    return errs

def _upload_to_cloudinary(owner_id: int, up: UploadFile) -> Optional[str]:
    """
    يرفع الصورة إلى Cloudinary ويُرجع secure_url
    """
    if not up or not up.filename:
        return None
    try:
        # يمكن الرفع مباشرة من الـ stream
        public_id = None  # اتركه None ليتولّى Cloudinary التسمية
        res = cloudinary.uploader.upload(
            up.file,
            folder=f"items/{owner_id}",
            public_id=public_id,
            resource_type="image",
        )
        url = res.get("secure_url")
        return url
    except Exception:
        # لو فشل، نُرجع None ونكمل بدون صورة
        return None

# ========= واجهة إنشاء عنصر =========
@router.get("/owner/items/new")
def item_new_get(
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_current_user(request, db)
    if not user:
        # غير مسجّل دخول
        return RedirectResponse(url="/login?next=/owner/items/new", status_code=303)

    # تأكد أن المستخدم موجود فعلياً في DB (لمنع خطأ FK)
    owner = db.get(User, user.id)
    if not owner:
        raise HTTPException(status_code=400, detail="حساب المستخدم غير موجود في قاعدة البيانات.")

    return request.app.templates.TemplateResponse(
        "owner_item_new.html",
        {
            "request": request,
            "title": "إضافة منتج جديد",
            "session_user": request.session.get("user"),
            "categories": CATEGORIES,
            "category_label": category_label,
            "errors": {},
            "form": {"title": "", "description": "", "city": "", "price_per_day": "", "category": "other"},
        },
    )

@router.post("/owner/items/new")
def item_new_post(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    city: str = Form(...),
    price_per_day: int = Form(...),
    category: str = Form(...),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    # 1) المستخدم
    user = _get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="يجب تسجيل الدخول.")

    owner = db.get(User, user.id)
    if not owner:
        # هذا هو أصل مشكلة FK عندك — الآن نوقف العملية برسالة واضحة
        raise HTTPException(status_code=400, detail="حساب المستخدم غير موجود في قاعدة البيانات.")

    # 2) تحقق المدخلات
    errors = _validate_basic(title, description, city, price_per_day, category)

    # تحقق امتداد الصورة (اختياري)
    img_url: Optional[str] = None
    if image and image.filename:
        ext = _ext_lower(image.filename)
        if ext and ext not in ALLOWED_IMAGE_EXTS:
            errors["image"] = "امتداد الصورة غير مدعوم."
    if errors:
        return request.app.templates.TemplateResponse(
            "owner_item_new.html",
            {
                "request": request,
                "title": "إضافة منتج جديد",
                "session_user": request.session.get("user"),
                "categories": CATEGORIES,
                "category_label": category_label,
                "errors": errors,
                "form": {
                    "title": title,
                    "description": description,
                    "city": city,
                    "price_per_day": price_per_day,
                    "category": category,
                },
            },
            status_code=400,
        )

    # 3) ارفع الصورة إلى Cloudinary (إن وجدت)
    if image and image.filename:
        img_url = _upload_to_cloudinary(owner.id, image)

    # 4) أنشئ الـ Item
    new_item = Item(
        owner_id=owner.id,                # مهم: استخدم ID موجود فعلياً
        title=title.strip(),
        description=description.strip(),
        city=city.strip(),
        price_per_day=int(price_per_day),
        category=category,
        image_path=img_url,               # Cloudinary secure_url أو None
        is_active="yes",                  # حسب سكيمتك (يبدو VARCHAR yes/no)
        created_at=datetime.utcnow(),
    )

    db.add(new_item)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        # لو رجع خطأ FK مرة ثانية، سيظهر هنا برسالة واضحة
        raise HTTPException(status_code=400, detail=f"تعذّر إنشاء المنتج: {e}")

    # 5) توجيه بعد النجاح
    # غيّر الوجهة لما يناسبك (قائمة منتجات المالك / صفحة العنصر)
    return RedirectResponse(url="/owner/items", status_code=303)

# ========= (اختياري) قائمة عناصر المالك =========
@router.get("/owner/items")
def owner_items_list(
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/owner/items", status_code=303)

    # تأكد أن المستخدم موجود
    owner = db.get(User, user.id)
    if not owner:
        raise HTTPException(status_code=400, detail="حساب المستخدم غير موجود في قاعدة البيانات.")

    items = (
        db.query(Item)
        .filter(Item.owner_id == owner.id)
        .order_by(Item.id.desc())
        .all()
    )

    return request.app.templates.TemplateResponse(
        "owner_items_list.html",
        {
            "request": request,
            "title": "منتجاتي",
            "session_user": request.session.get("user"),
            "items": items,
            "category_label": category_label,
        },
    )
