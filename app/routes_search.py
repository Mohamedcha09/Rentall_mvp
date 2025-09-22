# app/routes_search.py
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from .database import get_db
from .models import User, Item

router = APIRouter()

def _clean_name(first: str, last: str, uid: int) -> str:
    """
    يبني الاسم الكامل بشكل سليم حتى لو كان أحد الحقلين فاضي.
    (تم إصلاح السهو: كان f-string ينسى first_name عند وجوده)
    """
    f = (first or "").strip()
    l = (last or "").strip()
    if f and l:
        full = f"{f} {l}"
    else:
        full = f or l
    return full or f"User {uid}"

@router.get("/api/search")
def api_search(q: str = "", db: Session = Depends(get_db)):
    """
    بحث حيّ للمحرك (typeahead) — لا يتطلب تسجيل دخول، ولا يقرأ/يعدّل الـ session.
    يرجّع قوائم مبسطة: users + items، كل عنصر فيه url يُستخدم مباشرة في الواجهة.
    """
    q = (q or "").strip()
    if len(q) < 2:
        return {"users": [], "items": []}

    pattern = f"%{q}%"

    # --- مستخدمون (بالاسم الأول/الأخير)
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
        {
            "id": uid,
            "name": _clean_name(first, last, uid),
            "url": f"/users/{uid}",
        }
        for (uid, first, last) in users_rows
    ]

    # --- عناصر (بالعنوان/الوصف) مع شرط التفعيل
    items_rows = (
        db.query(Item.id, Item.title, Item.city)
        .filter(
            Item.is_active == "yes",
            or_(
                Item.title.ilike(pattern),
                Item.description.ilike(pattern),
            ),
        )
        .limit(8)
        .all()
    )

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

# (اختياري) صفحة نتائج كاملة /search لو كنت تستعملها في الواجهة
@router.get("/search")
def search_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    q = (q or "").strip()
    users = []
    items = []

    if len(q) >= 2:
        pattern = f"%{q}%"

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

        items_rows = (
            db.query(Item.id, Item.title, Item.city, Item.image_path)
            .filter(
                Item.is_active == "yes",
                or_(
                    Item.title.ilike(pattern),
                    Item.description.ilike(pattern),
                ),
            )
            .limit(24)
            .all()
        )
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

    # استخدم القالب الموجود عندك إن رغبت
    return request.app.templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "title": "نتائج البحث",
            "q": q,
            "users": users,
            "items": items,
            "session_user": request.session.get("user"),
        },
    )
