# app/routes_users.py
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from fastapi.templating import Jinja2Templates

# لو عندك مسار مختلف لـ get_db غيّره هنا
from app.db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _safe_first(db: Session, sql: str, params: dict):
    """تنفيذ استعلام واحد وإرجاع mapping().first() بأمان."""
    return db.execute(text(sql), params).mappings().first()


def _safe_all(db: Session, sql: str, params: dict):
    """تنفيذ استعلام واحد وإرجاع mapping().all() بأمان."""
    return db.execute(text(sql), params).mappings().all()


@router.get("/users/{user_id}")
def user_profile(request: Request, user_id: int, db: Session = Depends(get_db)):
    # -----------------------------
    # 1) جلب بيانات المستخدم بأمان
    # -----------------------------
    user = None

    # المحاولة 1: مع city
    try:
        user = _safe_first(
            db,
            """
            SELECT
                u.id,
                COALESCE(u.first_name,'')   AS first_name,
                COALESCE(u.last_name,'')    AS last_name,
                COALESCE(u.avatar_path,'')  AS avatar_path,
                COALESCE(u.city,'')         AS city,
                COALESCE(u.status,'')       AS status,
                u.created_at                AS created_at,
                COALESCE(u.bio,'')          AS bio
            FROM users u
            WHERE u.id = :uid
            LIMIT 1
            """,
            {"uid": user_id},
        )
    except OperationalError:
        # المحاولة 2: بدون city (لو العمود غير موجود)
        user = _safe_first(
            db,
            """
            SELECT
                u.id,
                COALESCE(u.first_name,'')   AS first_name,
                COALESCE(u.last_name,'')    AS last_name,
                COALESCE(u.avatar_path,'')  AS avatar_path,
                COALESCE(u.status,'')       AS status,
                u.created_at                AS created_at,
                COALESCE(u.bio,'')          AS bio
            FROM users u
            WHERE u.id = :uid
            LIMIT 1
            """,
            {"uid": user_id},
        )

    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    # إذا city مفقودة من الجدول، ضعه فارغ لتجنّب أخطاء في القالب
    if "city" not in user:
        user = {**user, "city": ""}

    # --------------------------------
    # 2) حساب الشارات (جديد / موثّق)
    # --------------------------------
    created_at = user.get("created_at")
    now = datetime.now(timezone.utc)
    is_new = False
    if isinstance(created_at, datetime):
        # لو التاريخ بلا tz، اعتبره UTC
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        is_new = (now - created_at) <= timedelta(days=60)

    is_verified = (user.get("status", "").lower() == "approved")

    # --------------------------------
    # 3) عناصر هذا المستخدم (Items)
    # --------------------------------
    # لو حقول city/category_label مفقودة بجدول items لا تسبب كراش:
    # سنحاول إحضارها أولاً، ثم نسقط للأبسط إن فشل.
    try:
        items = _safe_all(
            db,
            """
            SELECT
                i.id,
                COALESCE(i.title,'')           AS title,
                COALESCE(i.image_path,'')      AS image_path,
                COALESCE(i.city,'')            AS city,
                COALESCE(i.category_label,'')  AS category_label,
                COALESCE(i.price_per_day,0)    AS price_per_day,
                i.created_at
            FROM items i
            WHERE i.owner_id = :uid
            ORDER BY i.created_at DESC
            """,
            {"uid": user_id},
        )
    except OperationalError:
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
        # ضمن الحقول غير الموجودة كقِيَم افتراضية
        items = [
            {**it, "city": it.get("city", ""), "category_label": it.get("category_label", "")}
            for it in items
        ]

    # --------------------------------
    # 4) إحصاءات سريعة
    # --------------------------------
    try:
        stats = _safe_first(
            db,
            "SELECT COUNT(*) AS items_count FROM items WHERE owner_id = :uid",
            {"uid": user_id},
        ) or {"items_count": 0}
    except OperationalError:
        stats = {"items_count": len(items)}

    # --------------------------------
    # 5) تقييمات (اختياري، تحمّل عدم وجود الجدول)
    # --------------------------------
    rating_value = 0.0
    rating_count = 0
    try:
        rev = _safe_first(
            db,
            """
            SELECT
                COALESCE(AVG(r.rating),0) AS rating_value,
                COUNT(*)                  AS rating_count
            FROM reviews r
            WHERE r.target_user_id = :uid
            """,
            {"uid": user_id},
        )
        if rev:
            rating_value = float(rev.get("rating_value") or 0)
            rating_count = int(rev.get("rating_count") or 0)
    except OperationalError:
        pass  # لا يوجد جدول، تجاهل

    # --------------------------------
    # 6) حوّل created_at لنص آمن للقالب
    # --------------------------------
    created_at_str = ""
    if isinstance(created_at, datetime):
        created_at_str = created_at.strftime("%Y-%m-%d")

    # --------------------------------
    # 7) إرسال للتمبليت
    # --------------------------------
    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "user": user,
            "items": items,
            "stats": stats,
            "is_new": is_new,
            "is_verified": is_verified,
            "rating_value": rating_value,
            "rating_count": rating_count,
            "created_at_str": created_at_str,
        },
    )
