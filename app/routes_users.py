# app/routes_users.py
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from fastapi.templating import Jinja2Templates

from app.db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def _safe_first(db: Session, sql: str, params: dict):
    return db.execute(text(sql), params).mappings().first()

def _safe_all(db: Session, sql: str, params: dict):
    return db.execute(text(sql), params).mappings().all()

@router.get("/users/{user_id}")
def user_profile(request: Request, user_id: int, db: Session = Depends(get_db)):
    # ----------------------------------------------------
    # 1) اجلب فقط الأعمدة المضمونة الوجود لتفادي الأخطاء
    #    (city/bio غير مضمونة في سكيمتك الحالية)
    # ----------------------------------------------------
    user = _safe_first(
        db,
        """
        SELECT
            u.id,
            COALESCE(u.first_name,'')  AS first_name,
            COALESCE(u.last_name,'')   AS last_name,
            COALESCE(u.avatar_path,'') AS avatar_path,
            COALESCE(u.status,'')      AS status,
            u.created_at               AS created_at
        FROM users u
        WHERE u.id = :uid
        LIMIT 1
        """,
        {"uid": user_id},
    )
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    # city و bio غير موجودين في الجدول عندك، عيّنهم افتراضياً
    user = {
        **user,
        "city": "",
        "bio": "",
    }

    # ----------------------------------------------------
    # 2) حِساب الشارات
    # ----------------------------------------------------
    created_at = user.get("created_at")
    now = datetime.now(timezone.utc)
    is_new = False
    if isinstance(created_at, datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        is_new = (now - created_at) <= timedelta(days=60)
    is_verified = (user.get("status", "").lower() == "approved")

    created_at_str = ""
    if isinstance(created_at, datetime):
        created_at_str = created_at.strftime("%Y-%m-%d")

    # ----------------------------------------------------
    # 3) عناصر المستخدم — أيضاً نطلب الأعمدة المضمونة فقط
    # ----------------------------------------------------
    items = []
    try:
        items = _safe_all(
            db,
            """
            SELECT
                i.id,
                COALESCE(i.title,'')        AS title,
                COALESCE(i.image_path,'')   AS image_path,
                COALESCE(i.price_per_day,0) AS price_per_day,
                i.created_at
            FROM items i
            WHERE i.owner_id = :uid
            ORDER BY i.created_at DESC
            """,
            {"uid": user_id},
        )
    except OperationalError:
        items = []

    # أضف خصائص اختيارية قد يستعملها القالب (حتى لو غير موجودة في الجدول)
    items = [
        {
            **it,
            "city": it.get("city", ""),
            "category_label": it.get("category_label", ""),
        }
        for it in items
    ]

    # إحصائية بسيطة
    items_count = len(items)

    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "user": user,
            "items": items,
            "stats": {"items_count": items_count},
            "is_new": is_new,
            "is_verified": is_verified,
            "rating_value": 0.0,  # لو أضفت جدول reviews لاحقاً نحسبها
            "rating_count": 0,
            "created_at_str": created_at_str,
        },
    )
