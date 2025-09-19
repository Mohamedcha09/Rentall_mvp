# app/checkout.py
import os
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Item, Booking

router = APIRouter()

# ===============================
# صفحة الدفع لطلب حجز معيّن
# exemplo: /checkout/123
# ===============================
@router.get("/checkout/{booking_id}", response_class=HTMLResponse)
def checkout_detail(booking_id: int, request: Request, db: Session = Depends(get_db)):
    # لازم يكون المستخدم مسجّل دخول
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    # احضر بيانات الحجز + العنصر + المالك
    # ملاحظة: db.get متاحة في SQLAlchemy 2.x، ولو ما اشتغلت عندك استعمل query.get
    booking = db.get(Booking, booking_id) if hasattr(db, "get") else db.query(Booking).get(booking_id)
    if not booking:
        # لو الحجز غير موجود رجّع المستخدم للرئيسية
        return RedirectResponse(url="/", status_code=303)

    item = db.get(Item, booking.item_id) if hasattr(db, "get") else db.query(Item).get(booking.item_id)
    owner = db.get(User, booking.owner_id) if hasattr(db, "get") else db.query(User).get(booking.owner_id)

    # مفتاح Stripe العام لواجهة العميل (Elements)
    pk = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

    # أعرض القالب checkout_detail.html
    # هذا القالب عندك يستدعي /api/checkout/{booking_id}/intent من ملف pay_api.py
    return request.app.templates.TemplateResponse(
        "checkout_detail.html",
        {
            "request": request,
            "title": f"الدفع للحجز #{booking.id}",
            "booking": booking,
            "item": item,
            "owner": owner,
            "pk": pk,
            "session_user": sess,  # للنافبار
        },
    )


# ===============================
# إعدادات التحويل (Stripe Connect)
# exemplo: /payout/settings
# يصلّح خطأ 'user is undefined' بتمرير user للتمبلت
# ===============================
@router.get("/payout/settings", response_class=HTMLResponse)
def payout_settings(request: Request, db: Session = Depends(get_db)):
    # لازم يكون المستخدم مسجّل دخول
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    # جيب المستخدم من قاعدة البيانات
    user = db.get(User, sess["id"]) if hasattr(db, "get") else db.query(User).get(sess["id"])
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # مرّر user للتمبلت (كان هذا هو الناقص)
    return request.app.templates.TemplateResponse(
        "payout_settings.html",
        {
            "request": request,
            "title": "إعدادات التحويل",
            "user": user,          # <-- مهم: القالب يستعمله
            "session_user": sess,  # للنافبار
        },
    )
