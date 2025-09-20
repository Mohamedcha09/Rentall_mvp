# app/utils_badges.py
from datetime import datetime, timezone
from sqlalchemy import func
from .models import Rating, Booking, User

def _safe_days_since(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days

def count_five_star_received(user_id, db):
    return db.query(func.count(Rating.id)).filter(
        Rating.target_user_id == user_id,
        Rating.stars == 5
    ).scalar() or 0

def count_confirmed_returns_as_renter(user_id, db):
    """
    نحسب عدد الحجوزات التي أرجِعت بنجاح (كمستأجر).
    عدّل حالات/أسماء الحقول لو عندك اختلاف بسيط في الـ Booking.
    """
    return db.query(func.count(Booking.id)).filter(
        Booking.renter_id == user_id,
        Booking.status.in_(["returned","completed","closed"])  # عدّل حسب مشروعك
    ).scalar() or 0

def get_user_badges(user: User, db):
    """
    يحسب الشارات وفق القواعد التي طلبتها.
    يرجّع dict فيه flags/عدّادات لتستخدمها في القوالب.
    """
    days = _safe_days_since(user.created_at)
    five_star_count = count_five_star_received(user.id, db)
    returns_count = count_confirmed_returns_as_renter(user.id, db)
    is_admin = (user.role == "admin")

    # 1) البنفسجي بالأزرق (خاصة بالأدمين فقط)
    admin_purple_blue = is_admin

    # 2) الأصفر (مستخدم جديد لأول شهرين) ← تختفي بعد شهرين
    new_yellow = (not is_admin) and (days is not None) and (days < 60)

    # 3) PRO أخضر من شهرين إلى سنة (لغير الأدمين)
    pro_green = (not is_admin) and (days is not None) and (60 <= days < 365)

    # 4) PRO ذهبي بعد سنة (للجميع)
    pro_gold = (days is not None) and (days >= 365)

    # 5) البنفسجي بدون الأزرق (موثوق من الأدمين أو تلقائي بعد 20 تقييم 5 نجوم) — يُستثنى الأdmين
    # لو عندك فلاغ توثيق من لوحة الأdmين غير user.is_verified استبدله هنا.
    trusted_violet = (not is_admin) and ((getattr(user, "is_verified", False)) or (five_star_count >= 20))

    # 6) الخضراء (كمستأجر أنهى 10 إرجاعات مؤكدة)
    renter_green = (returns_count >= 10)

    # 7) البرتقالية (10 تقييمات خمس نجوم)
    orange_star = (five_star_count >= 10)

    # ضمان عدم اجتماع الأصفر مع PRO أخضر/ذهبي
    if pro_gold:
        new_yellow = False
        pro_green = False
    elif pro_green:
        new_yellow = False

    return {
        "days": days,
        "five_star_count": five_star_count,
        "returns_count": returns_count,

        "admin_purple_blue": admin_purple_blue,  # (١) أدمين
        "new_yellow": new_yellow,                # (٢) جديد < 60 يوم
        "pro_green": pro_green,                  # (٣) PRO أخضر (60..365)
        "pro_gold": pro_gold,                    # (٤) PRO ذهبي (>= 365)
        "trusted_violet": trusted_violet,        # (٥) بنفسجي بدون أزرق
        "renter_green": renter_green,            # (٦) أخضر (10 إرجاعات)
        "orange_star": orange_star,              # (٧) برتقالي (10 × ★5)
        "is_admin": is_admin,
    }
