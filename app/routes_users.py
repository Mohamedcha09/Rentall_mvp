# app/routes_users.py
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from sqlalchemy.exc import OperationalError

from .database import get_db
from .models import Item  # نستخدم ORM لعناصر المستخدم فقط
from .utils import category_label

router = APIRouter()

# =========================
# Helpers
# =========================
def _safe_first(db: Session, sql: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    ينفّذ SQL ويعيد أول صف بشكل dict.
    لو فشل (عمود غير موجود مثلاً)، يرجع None لنجرب استعلاماً بديلاً.
    """
    try:
        return db.execute(text(sql), params).mappings().first()
    except OperationalError:
        return None

def _safe_all(db: Session, sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        return list(db.execute(text(sql), params).mappings().all())
    except OperationalError:
        return []

def _is_new_user(created_at: Optional[datetime]) -> bool:
    if not created_at:
        return False
    try:
        return (datetime.utcnow() - created_at) <= timedelta(days=60)  # شهرين ≈ 60 يوم
    except Exception:
        return False

# =========================
# صفحة المستخدم /users/{id}
# =========================
@router.get("/users/{user_id}", response_class=HTMLResponse)
def user_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    """
    يعرض صفحة مستخدم:
      - الاسم + الشارات (توثيق، جديد)
      - نبذة/مدينة إن وجدت
      - عناصره النشطة
      - إحصائيات بسيطة (عدد العناصر)
    مع حماية ضد أعمدة غير موجودة في جدول users.
    """

    # المحاولة 1: كل الحقول (بما فيها city, bio)
    sql_primary = """
        SELECT
            u.id,
            COALESCE(u.first_name, '')  AS first_name,
            COALESCE(u.last_name, '')   AS last_name,
            COALESCE(u.avatar_path, '') AS avatar_path,
            COALESCE(u.city, '')        AS city,
            COALESCE(u.status, '')      AS status,
            u.created_at                AS created_at,
            COALESCE(u.bio, '')         AS bio,
            COALESCE(u.is_verified, 0)  AS is_verified
        FROM users u
        WHERE u.id = :uid
        LIMIT 1
    """
    user_row = _safe_first(db, sql_primary, {"uid": user_id})

    # المحاولة 2: بدون city/bio لو تسببوا بخطأ (بدون حذف ميزة، مجرد بديل تلقائي)
    if not user_row:
        sql_fallback = """
            SELECT
                u.id,
                COALESCE(u.first_name, '')  AS first_name,
                COALESCE(u.last_name, '')   AS last_name,
                COALESCE(u.avatar_path, '') AS avatar_path,
                COALESCE(u.status, '')      AS status,
                u.created_at                AS created_at,
                0                           AS is_verified
            FROM users u
            WHERE u.id = :uid
            LIMIT 1
        """
        user_row = _safe_first(db, sql_fallback, {"uid": user_id})

    if not user_row:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    # تفريغ القيم
    user: Dict[str, Any] = dict(user_row)
    first_name = user.get("first_name", "").strip()
    last_name = user.get("last_name", "").strip()
    full_name = (first_name + " " + last_name).strip() or "بدون اسم"

    # شارات
    created_at = user.get("created_at")
    is_new_yellow = _is_new_user(created_at)
    is_verified = bool(user.get("is_verified", 0))

    # عناصر المستخدم (نشطة فقط)
    items = (
        db.query(Item)
        .filter(Item.owner_id == user_id, Item.is_active == "yes")
        .order_by(Item.created_at.desc())
        .all()
    )
    for it in items:
        it.category_label = category_label(it.category)

    # إحصائيات / تقييمات اختيارية (بدون كسر لو الجدول غير موجود)
    stats = {"items_count": len(items)}
    try:
        sql_rating = """
            SELECT
                COUNT(*) AS reviews_count,
                COALESCE(AVG(r.stars), 0) AS avg_stars
            FROM ratings r
            WHERE r.target_user_id = :uid
        """
        rating_row = _safe_first(db, sql_rating, {"uid": user_id}) or {}
        stats["reviews_count"] = int(rating_row.get("reviews_count", 0) or 0)
        stats["avg_stars"] = float(rating_row.get("avg_stars", 0) or 0)
    except Exception:
        stats["reviews_count"] = 0
        stats["avg_stars"] = 0.0

    # تمرير كل شيء إلى القالب
    return request.app.templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "title": f"حساب {full_name}",
            "session_user": request.session.get("user"),
            "profile_user": user,            # صف المستخدم (id, names, avatar, status, created_at, city/bio إن وجدت)
            "is_new_yellow": is_new_yellow,  # شارة الأصفر (جديد)
            "is_verified": is_verified,      # شارة التوثيق
            "items": items,                  # عناصره
            "stats": stats,                  # إحصائيات
        },
    )
