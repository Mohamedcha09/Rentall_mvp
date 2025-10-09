# app/admin_deposits.py
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter(tags=["admin", "deposit"])

# =========================
# Helpers
# =========================
def _require_admin(request: Request) -> bool:
    u = request.session.get("user")
    return bool(u and u.get("role") == "admin")

def _sync_session_if_self(request: Request, user: User) -> None:
    """لو الأدمِن عدّل نفسه، حدّث الجلسة مباشرة."""
    sess = request.session.get("user")
    if not sess or sess.get("id") != user.id:
        return
    # قيَم تظهر في الواجهات
    sess["role"] = user.role
    sess["status"] = user.status
    # الحقل الجديد: is_deposit_manager
    try:
        sess["is_deposit_manager"] = bool(getattr(user, "is_deposit_manager", False))
    except Exception:
        pass

# =========================
# صفحة: إدارة متحكّمي الوديعة
# =========================
@router.get("/admin/deposit-managers")
def deposit_managers_index(request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    # كل المستخدمين + من لديه الصلاحية
    users = (
        db.query(User)
        .order_by(User.created_at.desc().nullslast())
        .all()
    )

    return request.app.templates.TemplateResponse(
        "admin_deposit_managers.html",
        {
            "request": request,
            "title": "إدارة متحكّمي الوديعة",
            "users": users,
            "session_user": request.session.get("user"),
        },
    )

# =========================
# POST: منح الصلاحية
# =========================
@router.post("/admin/deposit-managers/{user_id}/grant")
def grant_deposit_manager(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u:
        # لو عمود is_deposit_manager غير موجود في DB قديمة،
        # col_or_literal في models.py سيرجعه None — نحاول الحفظ إذا كان فعليًا موجودًا.
        try:
            u.is_deposit_manager = True
        except Exception:
            # لا شيء: في قواعد قديمة لن يُخزَّن، لكن لا نكسر التدفق.
            pass
        db.add(u)
        db.commit()
        _sync_session_if_self(request, u)

    return RedirectResponse(url="/admin/deposit-managers", status_code=303)

# =========================
# POST: سحب الصلاحية
# =========================
@router.post("/admin/deposit-managers/{user_id}/revoke")
def revoke_deposit_manager(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    u = db.query(User).get(user_id)
    if u:
        try:
            u.is_deposit_manager = False
        except Exception:
            pass
        db.add(u)
        db.commit()
        _sync_session_if_self(request, u)

    return RedirectResponse(url="/admin/deposit-managers", status_code=303)

# =========================
# API JSON (اختياري للاستخدام في واجهة Ajax)
# =========================
@router.get("/api/admin/deposit-managers")
def api_list_deposit_managers(request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    rows = (
        db.query(User)
        .order_by(User.created_at.desc().nullslast())
        .all()
    )
    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "name": f"{r.first_name} {r.last_name}".strip(),
            "email": r.email,
            "role": r.role,
            "status": r.status,
            "is_deposit_manager": bool(getattr(r, "is_deposit_manager", False)),
            "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
        })
    return JSONResponse({"items": items})

@router.post("/api/admin/deposit-managers/toggle")
def api_toggle_deposit_manager(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Form(...),
    enable: bool = Form(...),
):
    if not _require_admin(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    u = db.query(User).get(user_id)
    if not u:
        return JSONResponse({"error": "user_not_found"}, status_code=404)

    try:
        u.is_deposit_manager = bool(enable)
    except Exception:
        # في قاعدة قديمة بدون العمود، لن يتم التخزين
        return JSONResponse({"ok": False, "reason": "column_missing"}, status_code=200)

    db.add(u)
    db.commit()
    _sync_session_if_self(request, u)

    return JSONResponse({"ok": True, "user_id": u.id, "is_deposit_manager": bool(u.is_deposit_manager)})
