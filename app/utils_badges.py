# app/utils_badges.py
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from .models import User, Booking, Rating

# الحالات التي نعتبر فيها الحجز "مكتمل"
BOOKING_DONE_STATUSES = {"finished", "completed", "approved", "paid", "done"}

def _months_since(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    now = datetime.now(timezone.utc) if dt.tzinfo else datetime.utcnow()
    return max(0, (now - dt).days // 30)

def _finished_bookings_count(db: Session, user_id: int) -> int:
    q = db.query(Booking).filter(
        or_(Booking.renter_id == user_id, Booking.owner_id == user_id)
    )
    if hasattr(Booking, "status"):
        q = q.filter(Booking.status.in_(BOOKING_DONE_STATUSES))
    return q.count()

def _ratings_totals(db: Session, user_id: int) -> Tuple[int, int]:
    total = db.query(Rating).filter(Rating.rated_user_id == user_id).count()
    fives = (
        db.query(Rating)
        .filter(Rating.rated_user_id == user_id, Rating.stars == 5)
        .count()
    )
    return total, fives

def get_user_badges(user: User, db: Session) -> List[str]:
    """
    تُعيد قائمة أسماء صور الشارات حسب قواعدك:
      adm      → الأزرق (أدمن فقط)
      violet   → بنفسجي (توثيق من الأدمِن)
      jaune    → أصفر (حساب جديد < شهرين)
      ProVert  → برو أخضر (≥ شهرين وأقل من سنة)
      ProGold  → برو ذهبي (≥ سنة)
      Vert     → أخضر بدرع (استعمال الموقع ≥ 5 حجوزات مكتملة)
      orange   → برتقالي (≥ 20 تقييم وكلها 5 نجوم)

    ترجع الأسماء مطابقة للصور داخل static/img
    """
    badges: List[str] = []

    # 1) الأزرق (أدمن)
    if getattr(user, "role", None) == "admin" or getattr(user, "badge_admin", False):
        badges.append("adm")

    # 2) البنفسجي (توثيق من الأدمِن)
    if getattr(user, "is_verified", False) or getattr(user, "badge_purple_trust", False):
        badges.append("violet")

    # 3) شارات الزمن (أصفر/Pro أخضر/Pro ذهبي)
    months = _months_since(getattr(user, "created_at", None))
    if getattr(user, "badge_new_yellow", False) or months < 2:
        badges.append("jaune")
    elif getattr(user, "badge_pro_gold", False) or months >= 12:
        badges.append("ProGold")
    else:
        badges.append("ProVert")

    # 4) الخضراء (درع) — استعمال الموقع
    if getattr(user, "badge_renter_green", False):
        badges.append("Vert")
    else:
        if _finished_bookings_count(db, user.id) >= 5:
            badges.append("Vert")

    # 5) البرتقالية — التقييمات
    if getattr(user, "badge_orange_stars", False):
        badges.append("orange")
    else:
        total, fives = _ratings_totals(db, user.id)
        if total >= 20 and fiv
