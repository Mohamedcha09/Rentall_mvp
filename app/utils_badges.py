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
    Returns the list of badge image names you currently support:
      - 'jaune'  : New account (less than two months old)
      - 'violet' : Trusted/Verified (enabled by admin via is_verified or badge_purple_trust)

    Expected images:
      static/img/jaune.png
      static/img/violet.png
    """
    badges: List[str] = []

    # Purple: trust (admin-controlled)
    if bool(getattr(user, "is_verified", False)) or bool(getattr(user, "badge_purple_trust", False)):
        badges.append("violet")

    # Yellow: new (less than two months)
    months = _months_since(getattr(user, "created_at", None))
    if months < 2:
        badges.append("jaune")

    return badges
