# app/utils_badges.py
from datetime import datetime, timezone
from typing import List, Optional
from .models import User

def _months_since(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    now = datetime.now(timezone.utc) if getattr(dt, "tzinfo", None) else datetime.utcnow()
    return max(0, (now - dt).days // 30)

def get_user_badges(user: User, db=None) -> List[str]:
    """
    يعيد قائمة أسماء صور الشارات المتوفرة لديك فقط:
      - 'jaune'  : حساب جديد أقل من شهرين
      - 'violet' : ثقة/موثوق (يفعّلها الأدمِن عبر is_verified أو badge_purple_trust)

    الصور المتوقعة:
      static/img/jaune.png
      static/img/violet.png
    """
    badges: List[str] = []

    # البنفسجي: ثقة (إدارة الأدمِن)
    if bool(getattr(user, "is_verified", False)) or bool(getattr(user, "badge_purple_trust", False)):
        badges.append("violet")

    # الأصفر: جديد (أقل من شهرين)
    months = _months_since(getattr(user, "created_at", None))
    if months < 2:
        badges.append("jaune")

    return badges
