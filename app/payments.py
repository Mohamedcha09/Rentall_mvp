# app/payments.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Item

router = APIRouter()

# ===== Helpers =====
def require_login(request: Request):
    return request.session.get("user")

def require_approved(request: Request):
    u = request.session.get("user")
    return u and u.get("status") == "approved"

# ================================
# حساب المالك لاستلام الأموال (واجهة)
# ================================
@router.get("/wallet/connect")
def wallet_connect(request: Request):
    """
    صفحة مبسّطة تُظهر زر (ربط Stripe) — تبقي على قالبك الحالي إن رغبت،
    لكن الزر سيحوّل إلى /payout/connect/start الحقيقي.
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    return request.app.templates.TemplateResponse(
        "wallet_connect.html",
        {
            "request": request,
            "title": "إعداد حساب الاستلام",
            "session_user": u,
            "connect_start_url": "/payout/connect/start",
            "connect_refresh_url": "/payout/connect/refresh",
        }
    )

@router.post("/wallet/connect")
def wallet_connect_post(request: Request):
    """
    دعم لأي فورم قديم: نحول فورًا لمسار البدء الحقيقي في payout_connect.py
    """
    return RedirectResponse(url="/payout/connect/start", status_code=303)

@router.get("/payout/settings")
def payout_settings(request: Request):
    """
    صفحة إعدادات التحويل — تُظهر حالة الحساب من الـ session
    (تتحدّث تلقائيًا عبر الميدلوير في main.py بعد استدعاء /payout/connect/refresh).
    وتعرض أزرار (بدء/إعادة) الربط.
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    # نمرّر روابط الربط/التحديث للقالب:
    return request.app.templates.TemplateResponse(
        "payout_settings.html",
        {
            "request": request,
            "title": "إعدادات التحويل",
            "session_user": u,
            "connect_start_url": "/payout/connect/start",
            "connect_refresh_url": "/payout/connect/refresh",
        }
    )

# =========================================
# صفحة دفع التأمين/الحجز للمستأجر (Placeholder)
# =========================================
@router.get("/checkout/deposit/{item_id}")
def checkout_deposit(item_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    item = db.query(Item).get(item_id)
    if not item or item.is_active != "yes":
        return RedirectResponse(url="/items", status_code=303)

    # لاحقاً: اقرأ security_deposit الحقيقي من DB إن أضفت العمود.
    security_deposit = getattr(item, "security_deposit", None) or 100
    return request.app.templates.TemplateResponse(
        "checkout_deposit.html",
        {
            "request": request,
            "title": "تأمين/حجز",
            "session_user": u,
            "item": item,
            "security_deposit": security_deposit,
        }
    )

@router.post("/checkout/deposit/{item_id}")
def checkout_deposit_post(item_id: int, request: Request):
    # لاحقاً: إنشاء جلسة Stripe أو تفويض تأمين.
    return RedirectResponse(url="/my/rentals", status_code=303)

# =====================
# صفحات “لوحاتي”
# =====================
@router.get("/my/rentals")         # كمستأجر
def my_rentals(request: Request):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "my_rentals.html",
        {"request": request, "title": "طلباتي (مستأجر)", "session_user": u}
    )

@router.get("/my/orders")          # كمالك
def my_orders(request: Request):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "my_orders.html",
        {"request": request, "title": "طلباتي (مالك)", "session_user": u}
    )

# ================
# نزاع/بلاغ
# ================
@router.get("/dispute/new")
def dispute_new(request: Request):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "dispute_new.html",
        {"request": request, "title": "فتح نزاع", "session_user": u}
    )

@router.post("/dispute/new")
def dispute_new_post(request: Request, reason: str = Form(...)):
    # لاحقاً: نحفظ النزاع في DB ونعلم الأدمين
    return RedirectResponse(url="/my/rentals", status_code=303)

# ==============================
# لوحة أدمين للمدفوعات (Placeholder)
# ==============================
@router.get("/admin/payouts")
def admin_payouts(request: Request):
    u = request.session.get("user")
    if not (u and u.get("role") == "admin"):
        return RedirectResponse(url="/login", status_code=303)

    return request.app.templates.TemplateResponse(
        "admin_payouts.html",
        {"request": request, "title": "تحويلات/دفعات", "session_user": u}
    )