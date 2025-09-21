# app/routes_users.py
from fastapi import APIRouter, Depends, Request, HTTPException, Path
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi.templating import Jinja2Templates

from .db import get_db  # موجود عندك سابقًا

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/users/{user_id}")
def user_profile(
    request: Request,
    user_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    # جيب المستخدم
    user_sql = text("""
        SELECT id,
               COALESCE(first_name,'')  AS first_name,
               COALESCE(last_name,'')   AS last_name,
               COALESCE(avatar_path,'') AS avatar_path,
               COALESCE(status,'')      AS status
        FROM users
        WHERE id = :uid
        LIMIT 1
    """)
    user = db.execute(user_sql, {"uid": user_id}).mappings().first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    # عناصر هذا المستخدم
    items_sql = text("""
        SELECT id, title, city, price_per_day, COALESCE(image_path,'') AS image_path
        FROM items
        WHERE owner_id = :uid
        ORDER BY id DESC
        LIMIT 200
    """)
    items = db.execute(items_sql, {"uid": user_id}).mappings().all()

    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "title": f"{user['first_name']} {user['last_name']}".strip() or "المستخدم",
            "profile_user": user,
            "items": items,
        },
    )
