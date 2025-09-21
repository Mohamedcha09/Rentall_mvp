# app/routes_search.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from .db import get_db

router = APIRouter()

@router.get("/api/search")
def search(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    # جهّز الاستعلام بما يناسب محرّك القاعدة
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    q_str = q.strip()
    if not q_str:
        return {"users": [], "items": []}

    if dialect == "sqlite":
        # SQLite لا يدعم ILIKE -> نستخدم LOWER(..) LIKE
        q_like = f"%{q_str.lower()}%"
        users_sql = text("""
            SELECT id, TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS name
            FROM users
            WHERE LOWER(COALESCE(first_name,'')) LIKE :q
               OR LOWER(COALESCE(last_name,''))  LIKE :q
            LIMIT 5
        """)
        items_sql = text("""
            SELECT id, title, city
            FROM items
            WHERE LOWER(COALESCE(title,'')) LIKE :q
               OR LOWER(COALESCE(city,''))  LIKE :q
            LIMIT 5
        """)
        params = {"q": q_like}
    else:
        # Postgres وغيرها: ILIKE مدعوم
        q_like = f"%{q_str}%"
        users_sql = text("""
            SELECT id, CONCAT_WS(' ', first_name, last_name) AS name
            FROM users
            WHERE first_name ILIKE :q OR last_name ILIKE :q
            LIMIT 5
        """)
        items_sql = text("""
            SELECT id, title, city
            FROM items
            WHERE title ILIKE :q OR city ILIKE :q
            LIMIT 5
        """)
        params = {"q": q_like}

    users = db.execute(users_sql, params).mappings().all()
    items = db.execute(items_sql, params).mappings().all()

    return {
        "users": [
            {"id": u["id"], "name": u["name"], "url": f"/users/{u['id']}"}
            for u in users
        ],
        "items": [
            {"id": i["id"], "title": i["title"], "city": i.get("city"), "url": f"/items/{i['id']}"}
            for i in items
        ],
    }
