# app/admin_badges.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import User

router = APIRouter()

BADGE_FIELDS = [
    "badge_new_yellow",
    "badge_pro_green",
    "badge_pro_gold",
    "badge_purple_trust",
    "badge_renter_green",
    "badge_orange_stars",
    # ملاحظة: badge_admin إن أردتها يدويًا يمكنك إضافتها هنا أيضاً
]

def _require_admin(request: Request) -> dict | None:
    u = request.session.get("user")
    if not u or u.get("role") != "admin":
        return None
    return u

def _back(user_id: int | None = None):
    url = "/admin"
    if user_id:
        url += f"?focus={user_id}"
    return RedirectResponse(url=url, status_code=303)

@router.post("/admin/users/{user_id}/badges")
def admin_badges_save(user_id: int, request: Request, db: Session = Depends(get_db)):
    """يحفظ الشارات من الفورم (checkbox names = BADGE_FIELDS)."""
    if not _require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).get(user_id)
    if not user:
        return _back()

    form = request._form  # يتم تحميلها داخليًا بواسطة Starlette عند POST
    if form is None:
        # احتياط: لو لم تُحمّل، استخدم request.form()
        # لكن FastAPI يقوم بهذا نيابةً عنا عادةً.
        pass

    # عيّن False للجميع ثم فعّل الموجود في الفورم
    for f in BADGE_FIELDS:
        setattr(user, f, False)

    # فعِّل الموجودين في البيانات المُرسلة
    for name in BADGE_FIELDS:
        if name in request.query_params or name in (request._form or {}):
            setattr(user, name, True)

    # تعارض: الأصفر مع الـ Pro
    if getattr(user, "badge_pro_gold", False) or getattr(user, "badge_pro_green", False):
        setattr(user, "badge_new_yellow", False)

    db.commit()
    return _back(user_id)

@router.post("/admin/badges/{user_id}/clear")
def admin_badges_clear(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return RedirectResponse(url="/login", status_code=303)
    user = db.query(User).get(user_id)
    if not user:
        return _back()
    for f in BADGE_FIELDS:
        setattr(user, f, False)
    db.commit()
    return _back(user_id)

# (اختياري) نقاط تشغيل/إيقاف فردية
@router.post("/admin/badges/{user_id}/set/{name}")
def admin_badges_set(user_id: int, name: str, request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return RedirectResponse(url="/login", status_code=303)
    if name not in BADGE_FIELDS:
        return _back(user_id)
    u = db.query(User).get(user_id)
    if not u:
        return _back()
    setattr(u, name, True)
    if name in ("badge_pro_green","badge_pro_gold"):
        u.badge_new_yellow = False
    db.commit()
    return _back(user_id)

@router.post("/admin/badges/{user_id}/unset/{name}")
def admin_badges_unset(user_id: int, name: str, request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return RedirectResponse(url="/login", status_code=303)
    if name not in BADGE_FIELDS:
        return _back(user_id)
    u = db.query(User).get(user_id)
    if not u:
        return _back()
    setattr(u, name, False)
    db.commit()
    return _back(user_id)
