# app/items.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import os, secrets, shutil

from .database import get_db
from .models import Item, User
from .utils import CATEGORIES, category_label
from .utils_badges import get_user_badges

router = APIRouter()

UPLOADS_ROOT = os.environ.get("UPLOADS_DIR", "uploads")
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


# ================= قائمة العناصر =================
@router.get("/items")
def items_list(request: Request, db: Session = Depends(get_db), category: str = None):
    q = db.query(Item).filter(Item.is_active == "yes")
    current_category = None
    if category:
        q = q.filter(Item.category == category)
        current_category = category

    items = q.order_by(Item.created_at.desc()).all()
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

    items = db.query(Item).filter(Item.owner_id == u["id"]).order_by(Item.created_at.desc()).all()
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
    image: UploadFile = File(None)
):
    if not require_approved(request):
        return RedirectResponse(url="/login", status_code=303)

    u = request.session.get("user")
    img_path = None
    if image:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext in [".jpg", ".jpeg", ".png"]:
            fname = f"{u['id']}_{secrets.token_hex(8)}{ext}"
            fpath = os.path.join(ITEMS_DIR, fname)
            with open(fpath, "wb") as f:
                shutil.copyfileobj(image.file, f)
            img_path = fpath.replace("\\", "/")

    it = Item(
        owner_id=u["id"],
        title=title,
        description=description,
        city=city,
        price_per_day=price_per_day,
        image_path=img_path,
        is_active="yes",
        category=category
    )
    db.add(it)
    db.commit()
    return RedirectResponse(url=f"/items/{it.id}", status_code=303)
