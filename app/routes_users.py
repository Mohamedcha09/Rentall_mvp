# app/routes_users.py
from fastapi import APIRouter, Depends, Request, HTTPException, Path
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from fastapi.templating import Jinja2Templates

from .db import get_db  # تأكد موجودة

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def with_defaults(row: dict) -> dict:
    """
    يضيف مفاتيح افتراضية لو غير موجودة في جدول users لديك،
    حتى لا تكسر الواجهة الـ Jinja.
    """
    # حول RowMapping -> dict
    data = dict(row) if row is not None else {}
    # مفاتيح متوقعة في الواجهة
    data.setdefault("first_name", "")
    data.setdefault("last_name", "")
    data.setdefault("avatar_path", "")
    data.setdefault("city", "")
    data.setdefault("status", "")
    data.setdefault("bio", "")
    data.setdefault("created_at", None)
    return data

@router.get("/users/{user_id}")
def user_profile(
    request: Request,
    user_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    # ========= 1) معلومات المستخدم الأساسية =========
    # بدال ما نحدد أعمدة قد لا تكون موجودة، نجيب كل شيء:
    user_sql = text("""
        SELECT *
        FROM users
        WHERE id = :uid
        LIMIT 1
    """)
    user_row = db.execute(user_sql, {"uid": user_id}).mappings().first()
    if not user_row:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    user = with_defaults(user_row)

    # ========= 2) إحصائيات =========
    # آمنة: قد لا يكون عندك جدول reviews — نتعامل معه لاحقًا try/except
    # العناصر غالبًا موجودة
    items_count = 0
    items_count_sql = text("SELECT COUNT(*) AS c FROM items WHERE owner_id = :uid")
    try:
        items_count = db.execute(items_count_sql, {"uid": user_id}).scalar() or 0
    except OperationalError:
        items_count = 0

    total_reviews = 0
    avg_rating = 0.0
    try:
        review_stats_sql = text("""
            SELECT
              COALESCE(COUNT(*),0)  AS total_reviews,
              COALESCE(AVG(rating),0) AS avg_rating
            FROM reviews
            WHERE user_id = :uid
        """)
        rs = db.execute(review_stats_sql, {"uid": user_id}).mappings().first()
        if rs:
            total_reviews = int(rs.get("total_reviews", 0) or 0)
            avg_rating = float(rs.get("avg_rating", 0.0) or 0.0)
    except OperationalError:
        # ما في جدول reviews — عادي
        total_reviews = 0
        avg_rating = 0.0

    stats = {
        "total_items": items_count,
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
    }

    # ========= 3) عناصر هذا المستخدم =========
    items = []
    try:
        items_sql = text("""
            SELECT id,
                   COALESCE(title,'') AS title,
                   COALESCE(city,'')  AS city,
                   price_per_day,
                   COALESCE(image_path,'') AS image_path
            FROM items
            WHERE owner_id = :uid
            ORDER BY id DESC
            LIMIT 200
        """)
        items = db.execute(items_sql, {"uid": user_id}).mappings().all()
    except OperationalError:
        items = []

    # ========= 4) التقييمات (لو فيه جدول) =========
    reviews = []
    try:
        reviews_sql = text("""
            SELECT
                r.id,
                r.rating,
                COALESCE(r.comment,'') AS comment,
                r.created_at,
                rv.id AS reviewer_id,
                COALESCE(rv.first_name,'') AS reviewer_first_name,
                COALESCE(rv.last_name,'')  AS reviewer_last_name,
                COALESCE(rv.avatar_path,'') AS reviewer_avatar
            FROM reviews r
            JOIN users rv ON rv.id = r.reviewer_id
            WHERE r.user_id = :uid
            ORDER BY r.created_at DESC
            LIMIT 200
        """)
        reviews = db.execute(reviews_sql, {"uid": user_id}).mappings().all()
    except OperationalError:
        # مافيه reviews — عادي
        reviews = []

    full_name = f"{user.get('first_name','')} {user.get('last_name','')}".strip() or "المستخدم"

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
