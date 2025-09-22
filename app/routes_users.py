# app/routes_search.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from .database import get_db
from .models import User, Item

router = APIRouter()

# ---------- أداة صغيرة لتحسين اسم العرض ----------
def _display_name(first: str, last: str, uid: int) -> str:
    f = (first or "").strip()
    l = (last or "").strip()
    if f and l:
        return f"{f} {l}"
    if f:
        return f
    if l:
        return l
    return f"User {uid}"

# API خفيفة للاقتراحات (لا تلمس الجلسة)
@router.get("/api/search", response_class=JSONResponse)
def api_search(q: str = "", db: Session = Depends(get_db)):
    q = (q or "").strip()
    if not q:
        return {"users": [], "items": []}

    like = f"%{q}%"

    users = (
        db.query(User.id, User.first_name, User.last_name, User.avatar_path)
        .filter(
            or_(
                User.first_name.ilike(like),
                User.last_name.ilike(like),
                (User.first_name + " " + User.last_name).ilike(like),
            )
        )
        .order_by(User.first_name.asc())
        .limit(8)
        .all()
    )

    items = (
        db.query(Item.id, Item.title, Item.city, Item.image_path)
        .filter(
            Item.is_active == "yes",
            or_(Item.title.ilike(like), Item.description.ilike(like)),
        )
        .order_by(func.random())
        .limit(8)
        .all()
    )

    # نرجع شكل ثابت للواجهة: url + name/title + صور/مدينة إن وجدت
    return {
        "users": [
            {
                "id": u.id,
                "name": _display_name(u.first_name, u.last_name, u.id),
                "avatar": u.avatar_path or "",
                "url": f"/users/{u.id}",
            }
            for u in users
        ],
        "items": [
            {
                "id": it.id,
                "title": (it.title or "").strip(),
                "city": it.city or "",
                "image": it.image_path or "",
                "url": f"/items/{it.id}",
            }
            for it in items
        ],
    }

# صفحة نتائج البحث (عرض فقط – لا تعديل للـsession)
@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    q = (q or "").strip()
    users_list = []
    items_list = []
    if q:
        like = f"%{q}%"

        users = (
            db.query(User.id, User.first_name, User.last_name, User.avatar_path)
            .filter(
                or_(
                    User.first_name.ilike(like),
                    User.last_name.ilike(like),
                    (User.first_name + " " + User.last_name).ilike(like),
                )
            )
            .order_by(User.first_name.asc())
            .limit(20)
            .all()
        )
        # نوحّد الشكل لقالب search.html
        users_list = [
            {
                "id": u.id,
                "name": _display_name(u.first_name, u.last_name, u.id),
                "avatar_path": u.avatar_path or "",
                "url": f"/users/{u.id}",
            }
            for u in users
        ]

        items = (
            db.query(Item.id, Item.title, Item.city, Item.image_path)
            .filter(
                Item.is_active == "yes",
                or_(Item.title.ilike(like), Item.description.ilike(like)),
            )
            .order_by(func.random())
            .limit(24)
            .all()
        )
        items_list = [
            {
                "id": it.id,
                "title": (it.title or "").strip(),
                "city": it.city or "",
                "image_path": it.image_path or "",
                "url": f"/items/{it.id}",
            }
            for it in items
        ]

    # نمرر session_user للعرض فقط (بدون أي كتابة على الجلسة)
    return request.app.templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "title": "نتائج البحث",
            "q": q,
            "users": users_list,
            "items": items_list,
            "session_user": (request.session or {}).get("user"),
        },
    )
