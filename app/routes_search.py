# app/routes_search.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

# عدّل هذه الاستيرادات حسب مشروعك
from app.db import get_db
from app.models import User, Item  # تأكد من أسماء الموديلات والمسارات

router = APIRouter()

@router.get("/api/search")
def search(q: str = Query(""), limit: int = 8, db: Session = Depends(get_db)):
    q = (q or "").strip()
    if not q:
        return {"users": [], "items": []}

    # === بحث المستخدمين ===
    users = (
        db.query(User.id, User.first_name, User.last_name)
          .filter(
              or_(
                  User.first_name.ilike(f"%{q}%"),
                  User.last_name.ilike(f"%{q}%"),
                  (User.first_name + " " + User.last_name).ilike(f"%{q}%"),
              )
          )
          .order_by(User.first_name.asc())
          .limit(limit)
          .all()
    )

    # === بحث العناصر ===
    items = (
        db.query(Item.id, Item.title, Item.city)
          .filter(
              or_(
                  Item.title.ilike(f"%{q}%"),
                  Item.city.ilike(f"%{q}%"),
              )
          )
          .order_by(Item.created_at.desc())
          .limit(limit)
          .all()
    )

    # NB: غيّر روابط URLs لو مساراتك غير
    return {
        "users": [
            {
                "id": u.id,
                "name": f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or f"User {u.id}",
                "url": f"/users/{u.id}",   # إن كان عندك /profile/{id} بدّلها هنا
                "type": "user",
            } for u in users
        ],
        "items": [
            {
                "id": it.id,
                "title": it.title,
                "city": it.city,
                "url": f"/items/{it.id}",
                "type": "item",
            } for it in items
        ],
    }
