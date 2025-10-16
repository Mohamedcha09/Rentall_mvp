# app/admin_users.py
import os
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Document
from .email_service import send_email

router = APIRouter(tags=["admin-users"])

# ===== Helpers =====
def _me(request: Request) -> dict | None:
    return request.session.get("user")

def _admin_only(sess: dict | None):
    if not sess or (sess.get("role","").lower() != "admin"):
        raise HTTPException(status_code=403, detail="admin only")

# ===== صفحة لوحة الأدمِن لطلبات الموافقة =====
@router.get("/admin/users")
def admin_users_page(request: Request, db: Session = Depends(get_db)):
    sess = _me(request); _admin_only(sess)

    pending = db.query(User).filter(User.status != "approved").order_by(User.id.desc()).all()
    all_users = db.query(User).order_by(User.id.desc()).all()

    # نجلب آخر وثيقة (إن وجدت) لكل مستخدم لعرضها في القالب لو احتجت لاحقاً
    for u in all_users:
        try:
            u.latest_doc = None
            if u.documents:
                u.latest_doc = sorted(u.documents, key=lambda d: d.created_at or u.created_at, reverse=True)[0]
        except Exception:
            pass

    return request.app.templates.TemplateResponse(
        "admine_dashboard.html",
        {
            "request": request,
            "pending_users": pending,
            "all_users": all_users,
            "session_user": sess,
        }
    )

# ===== موافقة الحساب =====
@router.post("/admin/users/{user_id}/approve")
def admin_user_approve(user_id: int, request: Request, db: Session = Depends(get_db)):
    sess = _me(request); _admin_only(sess)

    u = db.query(User).get(user_id)
    if not u:
        raise HTTPException(404, "User not found")

    u.status = "approved"
    db.add(u); db.commit()

    # إيميل إشعار الموافقة
    try:
        site = os.getenv("SITE_URL") or os.getenv("BASE_URL") or ""
        html = f"""
        <div style="font-family:Tahoma,Arial,sans-serif;direction:rtl;text-align:right;line-height:1.8">
          <h3>تمت الموافقة على حسابك ✅</h3>
          <p>مرحبًا {u.first_name}! تم تفعيل حسابك بالكامل ويمكنك الآن إجراء الحجوزات.</p>
          <p style="margin:18px 0">
            <a href="{site or '/'}" style="background:#16a34a;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:700">
              ابدأ الآن
            </a>
          </p>
          <p style="color:#666;font-size:13px">شكرًا لاستخدامك RentAll 🌟</p>
        </div>
        """
        send_email(u.email, "تمت الموافقة على حسابك — RentAll", html, text_body="تمت الموافقة على حسابك ويمكنك الآن الحجز.")
    except Exception:
        pass

    return RedirectResponse(url="/admin/users", status_code=303)

# ===== رفض الحساب (اختياري) =====
@router.post("/admin/users/{user_id}/reject")
def admin_user_reject(user_id: int, request: Request, db: Session = Depends(get_db)):
    sess = _me(request); _admin_only(sess)
    u = db.query(User).get(user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.status = "rejected"
    db.add(u); db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

# ===== توثيق/إلغاء توثيق البريد يدويًا (اختياري) =====
@router.post("/admin/users/{user_id}/verify")
def admin_user_verify(user_id: int, request: Request, db: Session = Depends(get_db)):
    sess = _me(request); _admin_only(sess)
    u = db.query(User).get(user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.is_verified = True
    db.add(u); db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/admin/users/{user_id}/unverify")
def admin_user_unverify(user_id: int, request: Request, db: Session = Depends(get_db)):
    sess = _me(request); _admin_only(sess)
    u = db.query(User).get(user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.is_verified = False
    db.add(u); db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

# ===== منح/سحب صلاحية متحكم الوديعة (MD) — وفق قالبك =====
@router.post("/admin/users/{user_id}/deposit_manager/enable")
def admin_user_enable_md(user_id: int, request: Request, db: Session = Depends(get_db)):
    sess = _me(request); _admin_only(sess)
    u = db.query(User).get(user_id)
    if not u: raise HTTPException(404, "User not found")
    u.is_deposit_manager = True
    db.add(u); db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/admin/users/{user_id}/deposit_manager/disable")
def admin_user_disable_md(user_id: int, request: Request, db: Session = Depends(get_db)):
    sess = _me(request); _admin_only(sess)
    u = db.query(User).get(user_id)
    if not u: raise HTTPException(404, "User not found")
    u.is_deposit_manager = False
    db.add(u); db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

# ===== (اختياري) زر مراسلة المستخدم لاحقًا =====
@router.post("/admin/users/{user_id}/message")
def admin_user_message(user_id: int, request: Request, db: Session = Depends(get_db)):
    sess = _me(request); _admin_only(sess)
    # بإمكانك إعادة التوجيه لصفحة الرسائل مع user_id
    return RedirectResponse(url=f"/messages/start?user_id={user_id}", status_code=303)