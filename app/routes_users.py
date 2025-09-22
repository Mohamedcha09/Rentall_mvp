# app/routes_users.py
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from .database import get_db
from .models import User, Item

router = APIRouter()

def _safe_str(v, default=""):
    return (v or "").strip() if isinstance(v, str) else (v or default)

def _is_new_account(created_at: datetime | None, days:int = 60) -> bool:
    if not created_at:
        return False
    now = datetime.now(timezone.utc)
    # created_at قد تكون naive في SQLite — نتعامل معها كـ UTC
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (now - created_at) <= timedelta(days=days)

@router.get("/users/{user_id}")
def user_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    # 1) احضر المستخدم
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        # ما في مستخدم = 404
        raise HTTPException(status_code=404, detail="User not found")

    # 2) عناصره المفعّلة
    items = (
        db.query(Item)
        .filter(Item.owner_id == user.id, Item.is_active == "yes")
        .order_by(Item.created_at.desc().nullslast())
        .all()
    )

    # 3) إحصاءات بسيطة
    stats = {
        "items_count": db.query(func.count(Item.id)).filter(Item.owner_id == user.id, Item.is_active == "yes").scalar() or 0
    }

    # 4) حالة الشارات
    created_at = user.created_at
    is_new = _is_new_account(created_at, days=60)  # الشارة الصفراء خلال أول شهرين
    # التوثيق: إذا عندك حقل user.is_verified استعمله؛ وإلا نزّلها على status == 'approved'
    is_verified = bool(getattr(user, "is_verified", False)) or (user.status == "approved")

    # 5) قيم إضافية للعرض
    created_at_str = created_at.strftime("%Y-%m-%d") if created_at else ""

    # 6) (اختياري) تقييمات — إذا ما عندك جدول تقييمات حالياً، خلّها None
    rating_value = None
    rating_count = None

    # 7) مرّر كل شيء إلى القالب user.html
    return request.app.templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "title": f"{_safe_str(user.first_name, 'User')} {_safe_str(user.last_name)}",
            "user": user,
            "items": items,
            "stats": stats,
            "is_new": is_new,
            "is_verified": is_verified,
            "created_at_str": created_at_str,
            "rating_value": rating_value,
            "rating_count": rating_count,
            # نمرر session_user للعرض فقط (قراءة فقط)
            "session_user": (request.session or {}).get("user"),
        },
    )
