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
def user_profile(request: Request, user_id: int, db: Session = Depends(get_db)):
    # معلومات أساسية عن المستخدم
    user_sql = text("""
        SELECT
            u.id,
            COALESCE(u.first_name,'')  AS first_name,
            COALESCE(u.last_name,'')   AS last_name,
            COALESCE(u.avatar_path,'') AS avatar_path,
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

    # أعداد وتقييمات
    agg_sql = text("""
        SELECT
            (SELECT COUNT(*) FROM items i WHERE i.owner_id = :uid) AS items_count,
            (SELECT COUNT(*) FROM bookings b WHERE b.owner_id = :uid AND b.status = 'completed') AS completed_rentals,
            (SELECT ROUND(AVG(r.rating), 2) FROM reviews r WHERE r.target_user_id = :uid) AS avg_rating
    """)
    agg = db.execute(agg_sql, {"uid": user_id}).mappings().first()
    items_count = agg["items_count"] or 0
    completed_rentals = agg["completed_rentals"] or 0
    avg_rating = float(agg["avg_rating"]) if agg["avg_rating"] is not None else None

    # حساب الشارات
    created_at = user["created_at"]
    now = datetime.now(timezone.utc)
    is_new = False
    try:
        # created_at قد يكون naive; نتعامل مع الحالتين
        created_dt = created_at if isinstance(created_at, datetime) else None
        if created_dt is not None:
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            is_new = (now - created_dt).days < 14
    except Exception:
        is_new = False

    badges = {
        "verified": (user["status"] == "approved"),
        "new_user": is_new,
        "power_seller": (items_count >= 5),
        "trusted": (completed_rentals >= 3),
        "top_rated": (avg_rating is not None and avg_rating >= 4.5),
    }

    # عناصر المالك (تعرض أسفل الصفحة)
    items_sql = text("""
        SELECT
            i.id, i.title, i.city, i.price_per_day,
            COALESCE(i.image_path,'') AS image_path,
            COALESCE(i.category_label,'') AS category_label
        FROM items i
        WHERE i.owner_id = :uid
        ORDER BY i.id DESC
        LIMIT 50
    """)
    items = [dict(row) for row in db.execute(items_sql, {"uid": user_id}).mappings().all()]

    # التقييمات (اختياري)
    reviews_sql = text("""
        SELECT r.id, r.rating, COALESCE(r.comment,'') AS comment,
               r.created_at,
               COALESCE(u.first_name,'') AS reviewer_first,
               COALESCE(u.last_name,'')  AS reviewer_last
        FROM reviews r
        LEFT JOIN users u ON u.id = r.author_user_id
        WHERE r.target_user_id = :uid
        ORDER BY r.created_at DESC
        LIMIT 20
    """)
    reviews = [dict(row) for row in db.execute(reviews_sql, {"uid": user_id}).mappings().all()]

    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "user": user,
            "items": items,
            "reviews": reviews,
            "items_count": items_count,
            "completed_rentals": completed_rentals,
            "avg_rating": avg_rating,
            "badges": badges,
        }
    )