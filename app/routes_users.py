# app/routes_users.py
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from .database import get_db
from .models import User, Item, Rating  # ← أضفنا Rating

# ===== [إضافة] دعم إرسال الإيميل الموحّد (اختياري) =====
import os
BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")

try:
    # سيُنشأ لاحقًا في app/emailer.py — واجهة موحّدة HTML + نصي
    from .emailer import send_email as _templated_send_email  # signature: (to, subject, html_body, text_body=None, ...)
except Exception:
    _templated_send_email = None

def _send_email_safe(to: str | None, subject: str, html: str, text: str | None = None) -> bool:
    """
    محاولـة إرسال بريد عبر app/emailer.send_email إن وُجدت؛
    فشل الإرسال لا يؤثر على منطق المسارات الحالية.
    """
    if not to:
        return False
    try:
        if _templated_send_email:
            return bool(_templated_send_email(to, subject, html, text_body=text))
    except Exception:
        pass
    return False  # سقوط صامت

# ===== [اختياري] دوال مساعدة لإرسال رسائل إعادة التعيين/تأكيد الحذف =====
def send_reset_password_email(user: User, token: str) -> None:
    """
    تُستدعى من مسار/خدمة إعادة التعيين (إن وُجدت لديك).
    لا تضيف مسارات جديدة هنا — فقط أداة جاهزة للإرسال.
    """
    try:
        reset_link = f"{BASE_URL}/password/reset/confirm?token={token}"
        html = (
            f"<div style='font-family:Arial,Helvetica,sans-serif'>"
            f"<h3>إعادة تعيين كلمة المرور</h3>"
            f"<p>مرحبًا {(user.first_name or 'مستخدم')}</p>"
            f"<p>اضغط على الرابط التالي لإعادة تعيين كلمة المرور:</p>"
            f"<p><a href='{reset_link}'>{reset_link}</a></p>"
            f"<p style='color:#888;font-size:12px'>إذا لم تطلب ذلك، تجاهل هذه الرسالة.</p>"
            f"</div>"
        )
        text = (
            "إعادة تعيين كلمة المرور\n\n"
            f"الرابط: {reset_link}\n\n"
            "إذا لم تطلب ذلك، تجاهل هذه الرسالة."
        )
        _send_email_safe(user.email, "🔑 إعادة تعيين كلمة المرور", html, text)
    except Exception:
        pass

def send_delete_account_confirm_email(user: User, token: str) -> None:
    """
    تُستدعى من مسار/خدمة تأكيد حذف الحساب (إن وُجدت لديك).
    لا تضيف مسارات جديدة هنا — فقط أداة جاهزة للإرسال.
    """
    try:
        confirm_link = f"{BASE_URL}/account/delete/confirm?token={token}"
        html = (
            f"<div style='font-family:Arial,Helvetica,sans-serif'>"
            f"<h3>تأكيد حذف الحساب</h3>"
            f"<p>مرحبًا {(user.first_name or 'مستخدم')}</p>"
            f"<p>لتأكيد حذف حسابك نهائيًا، اضغط على الرابط التالي:</p>"
            f"<p><a href='{confirm_link}'>{confirm_link}</a></p>"
            f"<p style='color:#a00'>تحذير: هذا الإجراء لا يمكن التراجع عنه.</p>"
            f"</div>"
        )
        text = (
            "تأكيد حذف الحساب\n\n"
            f"رابط التأكيد: {confirm_link}\n\n"
            "تحذير: هذا الإجراء لا يمكن التراجع عنه."
        )
        _send_email_safe(user.email, "❌ تأكيد حذف الحساب", html, text)
    except Exception:
        pass
# ===== /إضافات البريد =====

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
    created_at = getattr(user, "created_at", None)
    is_new = _is_new(created_at, days=60)  # الشارة الصفراء لأول شهرين
    is_verified = bool(getattr(user, "is_verified", False)) or (user.status == "approved")

    # 5) عرض تاريخ الإنشاء
    created_at_str = created_at.strftime("%Y-%m-%d") if created_at else ""

    # 6) (اختياري) قيم تقييم قديمة إن كانت مستخدمة في القالب
    rating_value = None
    rating_count = None

    # 7) تقييمه كمستأجر (نعتمد جدول Rating الموجود لديك)
    #    التقييمات التي تلقاها هذا المستخدم: العمود هو rated_user_id
    renter_avg = (
        db.query(func.coalesce(func.avg(Rating.stars), 0))
        .filter(Rating.rated_user_id == user.id)
        .scalar()
        or 0
    )
    renter_cnt = (
        db.query(func.count(Rating.id))
        .filter(Rating.rated_user_id == user.id)
        .scalar()
        or 0
    )
    renter_reviews = (
        db.query(Rating)
        .filter(Rating.rated_user_id == user.id)
        .order_by(Rating.created_at.desc())
        .limit(30)
        .all()
    )

    # 8) سياق القالب
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
        # تقييمات/تعليقات تخص هذا المستخدم كمستأجر
        "renter_reviews_avg": round(float(renter_avg), 2),
        "renter_reviews_count": int(renter_cnt),
        "renter_reviews": renter_reviews,
    }

    return request.app.templates.TemplateResponse("user.html", context)
