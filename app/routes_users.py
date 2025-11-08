# app/routes_users.py
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from .database import get_db
from .models import User, Item, UserReview   # ← we used UserReview instead of Rating

# ===== [Optional: unified email sender] =====
import os
BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")

try:
    from .emailer import send_email as _templated_send_email
except Exception:
    _templated_send_email = None

def _send_email_safe(to: str | None, subject: str, html: str, text: str | None = None) -> bool:
    if not to:
        return False
    try:
        if _templated_send_email:
            return bool(_templated_send_email(to, subject, html, text_body=text))
    except Exception:
        pass
    return False

router = APIRouter()

def _clean_str(v, default=""):
    if isinstance(v, str):
        return v.strip()
    return default if v is None else str(v)

def _is_new(created_at: datetime | None, days: int = 60) -> bool:
    if not created_at:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - created_at) <= timedelta(days=days)

@router.get("/users/{user_id}")
def user_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    # 1) the user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2) their active items
    items = (
        db.query(Item)
        .filter(Item.owner_id == user.id, Item.is_active == "yes")
        .order_by(Item.created_at.desc().nullslast())
        .all()
    )

    # 3) simple stats
    items_count = (
        db.query(func.count(Item.id))
        .filter(Item.owner_id == user.id, Item.is_active == "yes")
        .scalar()
        or 0
    )
    stats = {"items_count": items_count}

    # 4) badges/status
    created_at = getattr(user, "created_at", None)
    is_new = _is_new(created_at, days=60)
    is_verified = bool(getattr(user, "is_verified", False)) or (user.status == "approved")
    created_at_str = created_at.strftime("%Y-%m-%d") if created_at else ""

    # 5) their rating **as a renter** from UserReview table
    #    target_user_id = the renter who received the review
    renter_avg = (
        db.query(func.coalesce(func.avg(UserReview.stars), 0.0))
        .filter(UserReview.target_user_id == user.id)
        .scalar()
        or 0.0
    )
    renter_cnt = (
        db.query(func.count(UserReview.id))
        .filter(UserReview.target_user_id == user.id)
        .scalar()
        or 0
    )
    renter_reviews = (
        db.query(UserReview)
        .filter(UserReview.target_user_id == user.id)
        .order_by(UserReview.created_at.desc().nullslast())
        .limit(30)
        .all()
    )

    context = {
        "request": request,
        "title": f"{_clean_str(user.first_name, 'User')} {_clean_str(user.last_name)}",
        "user": user,
        "profile_user": user,
        "items": items,
        "stats": stats,
        "is_new": is_new,
        "is_verified": is_verified,
        "created_at_str": created_at_str,
        "rating_value": None,
        "rating_count": None,
        "session_user": (request.session or {}).get("user"),
        # owner reviews for this user as a renter:
        "renter_reviews_avg": round(float(renter_avg), 2),
        "renter_reviews_count": int(renter_cnt),
        "renter_reviews": renter_reviews,
    }

    # Note: your profile display template is named user.html
    return request.app.templates.TemplateResponse("user.html", context)
