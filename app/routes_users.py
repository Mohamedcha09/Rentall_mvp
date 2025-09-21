# app/routes_users.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from .database import get_db

router = APIRouter()

def _safe_first(db: Session, sql: str, params: dict):
    try:
        return db.execute(text(sql), params).mappings().first()
    except Exception:
        return None

def _safe_all(db: Session, sql: str, params: dict):
    try:
        return db.execute(text(sql), params).mappings().all()
    except Exception:
        return []

@router.get("/users/{user_id}", response_class=HTMLResponse)
def user_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    # ===== 1) بيانات المستخدم (حقول مؤكدة الوجود فقط) =====
    user_sql = """
        SELECT
            u.id,
            COALESCE(u.first_name,'')   AS first_name,
            COALESCE(u.last_name,'')    AS last_name,
            COALESCE(u.avatar_path,'')  AS avatar_path,
            COALESCE(u.status,'')       AS status,
            u.created_at                AS created_at,
            COALESCE(u.is_verified,0)   AS is_verified,
            COALESCE(u.badge_new_yellow,0) AS badge_new_yellow
        FROM users u
        WHERE u.id = :uid
        LIMIT 1
    """
    profile_user = _safe_first(db, user_sql, {"uid": user_id})
    if not profile_user:
        return HTMLResponse("<h3>المستخدم غير موجود</h3>", status_code=404)

    # ===== 2) عناصره =====
    items_sql = """
        SELECT
            i.id,
            i.title,
            i.price_per_day,
            i.created_at,
            COALESCE(i.image_path,'') AS image_path,
            COALESCE(i.category,'')   AS category
        FROM items i
        WHERE i.owner_id = :uid
          AND COALESCE(i.is_active,'yes') = 'yes'
        ORDER BY i.created_at DESC
        LIMIT 24
    """
    items = _safe_all(db, items_sql, {"uid": user_id})
    for it in items:
        it["category_label"] = it.get("category", "")

    # ===== 3) إحصائيات بسيطة =====
    cnt = _safe_first(db, "SELECT COUNT(*) AS items_count FROM items WHERE owner_id=:uid AND COALESCE(is_active,'yes')='yes'", {"uid": user_id})
    stats = {"items_count": cnt["items_count"] if cnt else 0}

    # ===== 4) تقييمات (اختياري) =====
    r = _safe_first(db, "SELECT COUNT(*) AS rating_count, AVG(rating) AS rating_value FROM ratings WHERE target_user_id=:uid", {"uid": user_id})
    rating_count = r["rating_count"] if r and r["rating_count"] is not None else 0
    rating_value = float(r["rating_value"]) if r and r["rating_value"] is not None else 0.0

    # ===== 5) الشارات =====
    created_at = profile_user.get("created_at")
    is_new = False
    if created_at:
        try:
            is_new = (datetime.utcnow() - created_at) <= timedelta(days=60)
        except Exception:
            is_new = False
    is_verified = bool(profile_user.get("is_verified")) or (profile_user.get("status") == "approved")

    return request.app.templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "title": f"{profile_user.get('first_name','')} {profile_user.get('last_name','')}".strip() or "الملف الشخصي",
            "profile_user": profile_user,           # ← اسم جديد لتجنّب التعارض
            "items": items,
            "stats": stats,
            "rating_count": rating_count,
            "rating_value": rating_value,
            "is_new": is_new,
            "is_verified": is_verified,
            "created_at_str": (created_at.strftime("%Y-%m-%d") if created_at else ""),
            "session_user": request.session.get("user"),
        },
    )
