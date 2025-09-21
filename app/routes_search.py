# app/routes_search.py
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from .db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def _run_search(q: str, db: Session):
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    q_str = (q or "").strip()
    if not q_str:
        return {"users": [], "items": []}

    if dialect == "sqlite":
        like = f"%{q_str.lower()}%"
        users_sql = text("""
            SELECT id,
                   TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS name,
                   COALESCE(avatar_path, '') AS avatar_path
            FROM users
            WHERE LOWER(COALESCE(first_name,'')) LIKE :q
               OR LOWER(COALESCE(last_name,''))  LIKE :q
            ORDER BY id DESC
            LIMIT 20
        """)
        items_sql = text("""
            SELECT id, title, city, price_per_day, COALESCE(image_path,'') AS image_path
            FROM items
            WHERE LOWER(COALESCE(title,'')) LIKE :q
               OR LOWER(COALESCE(city,''))  LIKE :q
            ORDER BY id DESC
            LIMIT 20
        """)
        params = {"q": like}
    else:
        like = f"%{q_str}%"
        users_sql = text("""
            SELECT id,
                   CONCAT_WS(' ', first_name, last_name) AS name,
                   COALESCE(avatar_path, '') AS avatar_path
            FROM users
            WHERE first_name ILIKE :q OR last_name ILIKE :q
            ORDER BY id DESC
            LIMIT 20
        """)
        items_sql = text("""
            SELECT id, title, city, price_per_day, COALESCE(image_path,'') AS image_path
            FROM items
            WHERE title ILIKE :q OR city ILIKE :q
            ORDER BY id DESC
            LIMIT 20
        """)
        params = {"q": like}

    users = db.execute(users_sql, params).mappings().all()
    items = db.execute(items_sql, params).mappings().all()
    return {"users": users, "items": items}

# صفحة النتائج المقسومة قسمين
@router.get("/search")
def search_page(request: Request, q: str = Query("", min_length=0), db: Session = Depends(get_db)):
    data = _run_search(q, db) if q else {"users": [], "items": []}
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "title": "نتائج البحث",
            "q": q,
            "users": data["users"],
            "items": data["items"],
        },
    )

# API اختيارية (لو تحتاجها)
@router.get("/api/search")
def search_api(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    data = _run_search(q, db)
    return {
        "users": [
            {"id": u["id"], "name": u["name"], "avatar_path": u["avatar_path"], "url": f"/users/{u['id']}"}
            for u in data["users"]
        ],
        "items": [
            {"id": i["id"], "title": i["title"], "city": i.get("city"),
             "price_per_day": i.get("price_per_day"),
             "image_path": i.get("image_path"),
             "url": f"/items/{i['id']}"}
            for i in data["items"]
        ],
    }
