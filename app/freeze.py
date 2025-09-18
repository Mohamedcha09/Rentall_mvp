# app/freeze.py
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from .database import get_db
from .models import FreezeDeposit, Item, User

router = APIRouter()

def require_login(request: Request):
    return request.session.get("user")

def require_admin(request: Request) -> bool:
    u = request.session.get("user")
    return bool(u and u.get("role") == "admin")

# ====== واجهة المستخدم ======
@router.get("/freeze")
def freeze_list(request: Request, db: Session = Depends(get_db)):
    """
    صفحة Placeholder: تعرض كل عمليات "الضمان" الخاصة بالمستخدم الحالي.
    لا توجد عمليات مالية—مجرد تسجيل وواجهة توضيحية.
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    deposits = (
        db.query(FreezeDeposit)
        .filter(FreezeDeposit.user_id == u["id"])
        .order_by(FreezeDeposit.created_at.desc())
        .all()
    )
    return request.app.templates.TemplateResponse(
        "freeze.html",
        {
            "request": request,
            "title": "الضمانات (Placeholder)",
            "deposits": deposits,
            "session_user": u,
        }
    )

@router.post("/freeze/create")
def freeze_create(
    request: Request,
    db: Session = Depends(get_db),
    item_id: int = Form(0),
    amount: int = Form(0),
    note: str = Form("")
):
    """
    إنشاء سجل ضمان "شكلي" (planned). لا يوجد أي سحب/تجميد حقيقي.
    الهدف فقط تجهيز الواجهة المستقبلية.
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    dep = FreezeDeposit(
        user_id=u["id"],
        item_id=item_id if item_id else None,
        amount=amount if amount and amount > 0 else 0,
        status="planned",
        note=(note or "").strip() or None,
    )
    db.add(dep)
    db.commit()
    return RedirectResponse(url="/freeze", status_code=303)

# ====== لوحة الأدمين ======
@router.get("/admin/freeze")
def admin_freeze_list(request: Request, db: Session = Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    deposits = (
        db.query(FreezeDeposit)
        .order_by(FreezeDeposit.created_at.desc())
        .all()
    )
    return request.app.templates.TemplateResponse(
        "admin_freeze.html",
        {
            "request": request,
            "title": "إدارة الضمانات (Placeholder)",
            "deposits": deposits,
            "session_user": request.session.get("user"),
        }
    )

@router.post("/admin/freeze/{dep_id}/status")
def admin_change_freeze_status(dep_id: int, request: Request, db: Session = Depends(get_db), status: str = Form(...), note: str = Form("")):
    if not require_admin(request):
        return RedirectResponse(url="/login", status_code=303)

    dep = db.query(FreezeDeposit).get(dep_id)
    if dep:
        if status in ["planned", "held", "released", "canceled"]:
            dep.status = status
        dep.note = (note or "").strip() or dep.note
        dep.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/admin/freeze", status_code=303)
