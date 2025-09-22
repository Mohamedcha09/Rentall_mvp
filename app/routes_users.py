# app/routes_users.py
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from .database import get_db
from .models import User, Item

router = APIRouter()

def _clean_str(v, default=""):
    if isinstance(v, str):
        return v.strip()
    return default if v is None else str(v)

def _is_new(created_at: datetime | None, days: int = 60) -> bool:
    if not created_at:
        return False
    # في SQLite قد يكون created_at بدون timezone ـ نتعامل معه كـ UTC
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - created_at) <= timedelta(days=days)

@router.get("/users/{user_id}")
def user_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    # 1) احضر المستخدم
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2) عناصره المفعّلة
    items = (
        db.query(Item)
        .filter(Item.owner_id == user.id, Item.is_active == "yes")
        .order_by(Item.created_at.desc().nullslast())
        .all()
    )

    # 3) إحصاءات
    items_count = (
        db.query(func.count(Item.id))
        .filter(Item.owner_id == user.id, Item.is_active == "yes")
        .scalar()
        or 0
    )
    stats = {"items_count": items_count}

    # 4) الشارات
    created_at = user.created_at
    is_new = _is_new(created_at, days=60)  # الشارة الصفراء لأول شهرين
    is_verified = bool(getattr(user, "is_verified", False)) or (user.status == "approved")

    # 5) عرض تاريخ الإنشاء
    created_at_str = created_at.strftime("%Y-%m-%d") if created_at else ""

    # 6) (اختياري) التقييمات إن لم تكن موجودة حالياً
    rating_value = None
    rating_count = None

    # 7) مرر المتغيّرات للقالب — لاحظ أننا نمرر كلا الاسمين: user و profile_user
    context = {
        "request": request,
        "title": f"{_clean_str(user.first_name, 'User')} {_clean_str(user.last_name)}",
        "user": user,                 # لتمبليتات تعتمد على user
        "profile_user": user,         # لتمبليتات تعتمد على profile_user
        "items": items,
        "stats": stats,
        "is_new": is_new,
        "is_verified": is_verified,
        "created_at_str": created_at_str,
        "rating_value": rating_value,
        "rating_count": rating_count,
        # نمرر session_user للعرض فقط (قراءة) بدون تعديل الجلسة
        "session_user": (request.session or {}).get("user"),
    }

    return request.app.templates.TemplateResponse("user.html", context)
