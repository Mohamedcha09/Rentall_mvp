# app/routes_search.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from .database import get_db
from .models import User, Item

router = APIRouter()

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
        db.query(Item.id, Item.title, Item.image_path)
        .filter(
            Item.is_active == "yes",
            or_(Item.title.ilike(like), Item.description.ilike(like)),
        )
        .order_by(func.random())
        .limit(8)
        .all()
    )

    return {
        "users": [
            {
                "id": u.id,
                "name": f"{u.first_name or ''} {u.last_name or ''}".strip(),
                "avatar": u.avatar_path or "",
            }
            for u in users
        ],
        "items": [
            {
                "id": it.id,
                "title": it.title,
                "image": it.image_path or "",
            }
            for it in items
        ],
    }

# صفحة نتائج البحث (عرض فقط – لا تعديل للـsession)
@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    q = (q or "").strip()
    users = []
    items = []
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
        items = (
            db.query(Item)
            .filter(
                Item.is_active == "yes",
                or_(Item.title.ilike(like), Item.description.ilike(like)),
            )
            .order_by(func.random())
            .limit(24)
            .all()
        )

    # مَرِّر session_user للتمبليت فقط للعرض — بدون لمس request.session
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
