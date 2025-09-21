# app/routes_users.py
from fastapi import APIRouter, Depends, Request, HTTPException, Path
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi.templating import Jinja2Templates

from .db import get_db  # تأكد موجودة

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/users/{user_id}")
def user_profile(
    request: Request,
    user_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    # ===== 1) معلومات المستخدم الأساسية
    # TODO: عدّل أسماء الأعمدة لو مختلفة عندك
    user_sql = text("""
        SELECT
            u.id,
            COALESCE(u.first_name,'')  AS first_name,
            COALESCE(u.last_name,'')   AS last_name,
            COALESCE(u.avatar_path,'') AS avatar_path,
            COALESCE(u.city,'')        AS city,
            COALESCE(u.status,'')      AS status,
            u.created_at               AS created_at,
            COALESCE(u.bio,'')         AS bio
        FROM users u
        WHERE u.id = :uid
        LIMIT 1
    """)
    user = db.execute(user_sql, {"uid": user_id}).mappings().first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    # ===== 2) إحصائيات سريعة (عدد العناصر + عدد/متوسط التقييم)
    # TODO: لو جدول/أسماء أعمدة مختلفة للتقييمات، عدّل هنا
    stats_sql = text("""
        WITH item_counts AS (
            SELECT COUNT(*)::int AS total_items
            FROM items
            WHERE owner_id = :uid
        ),
        review_stats AS (
            SELECT
                COALESCE(COUNT(*),0)::int AS total_reviews,
                COALESCE(AVG(rating),0)::float AS avg_rating
            FROM reviews
            WHERE user_id = :uid
        )
        SELECT item_counts.total_items,
               review_stats.total_reviews,
               review_stats.avg_rating
        FROM item_counts, review_stats
    """)
    stats = db.execute(stats_sql, {"uid": user_id}).mappings().first() or {
        "total_items": 0, "total_reviews": 0, "avg_rating": 0.0
    }

    # ===== 3) عناصر هذا المستخدم
    items_sql = text("""
        SELECT id, title, city, price_per_day, COALESCE(image_path,'') AS image_path
        FROM items
        WHERE owner_id = :uid
        ORDER BY id DESC
        LIMIT 200
    """)
    items = db.execute(items_sql, {"uid": user_id}).mappings().all()

    # ===== 4) التقييمات (مع بيانات المقيِّم)
    # TODO: عدّل أسماء الجدول/الأعمدة لو مختلفة
    reviews_sql = text("""
        SELECT
            r.id,
            r.rating,
            COALESCE(r.comment,'')     AS comment,
            r.created_at               AS created_at,
            rv.id                      AS reviewer_id,
            COALESCE(rv.first_name,'') AS reviewer_first_name,
            COALESCE(rv.last_name,'')  AS reviewer_last_name,
            COALESCE(rv.avatar_path,'')AS reviewer_avatar
        FROM reviews r
        JOIN users   rv ON rv.id = r.reviewer_id
        WHERE r.user_id = :uid
        ORDER BY r.created_at DESC
        LIMIT 200
    """)
    reviews = db.execute(reviews_sql, {"uid": user_id}).mappings().all()

    # تنسيق بسيط للعنوان
    full_name = f"{user['first_name']} {user['last_name']}".strip() or "المستخدم"

    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "title": full_name,
            "profile_user": user,
            "stats": stats,
            "items": items,
            "reviews": reviews,
        },
    )
