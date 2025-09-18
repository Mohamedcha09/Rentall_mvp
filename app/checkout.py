# app/checkout.py
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from .database import get_db
from .models import Item, User ,Order # لا نحتاج جداول إضافية الآن (طلب تجريبي)
router = APIRouter()

def require_login(request: Request):
    return request.session.get("user")

@router.get("/checkout/start")
def checkout_start(request: Request, db: Session = Depends(get_db), item_id: int = 0, days: int = 1):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    item = db.query(Item).get(item_id)
    if not item or item.is_active != "yes":
        return RedirectResponse(url="/", status_code=303)

    # احسب فترة الإيجار تجريبياً
    days = max(1, int(days or 1))
    start_date = datetime.utcnow().date()
    end_date = start_date + timedelta(days=days)
    total = (item.price_per_day or 0) * days

    return request.app.templates.TemplateResponse(
        "checkout_details.html",
        {
            "request": request,
            "title": "إتمام الاستئجار",
            "session_user": u,
            "item": item,
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
            "total": total,
        },
    )

# مجرد تأكيد صوري للطلب (بدون حفظ DB الآن)
@router.post("/checkout/confirm")
def checkout_confirm(
    request: Request,
    db: Session = Depends(get_db),
    item_id: int = Form(...),
    days: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    price_per_day: int = Form(...),
    total: int = Form(...)
):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    item = db.query(Item).get(item_id)
    if not item or item.is_active != "yes":
        return RedirectResponse(url="/", status_code=303)

    # أنشئ الطلب
    order = Order(
        item_id=item.id,
        renter_id=u["id"],
        owner_id=item.owner_id,
        days=int(days),
        start_date=start_date,   # FastAPI سيحوّلها Date أو استخدم datetime.strptime إن أردت
        end_date=end_date,
        price_per_day=int(price_per_day),
        total_amount=int(total),
        status="pending"
    )
    db.add(order)
    db.commit()

    return RedirectResponse(url="/my_orders", status_code=303)

# صفحات المتابعة (عن قريب سنربطها بقاعدة بيانات)
@router.get("/my_orders")
def my_orders(request: Request, db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    orders = (
        db.query(Order).filter(Order.renter_id == u["id"]).order_by(Order.created_at.desc()).all()
    )

    # نحضّر بيانات العرض بشكل مبسّط
    view = []
    for o in orders:
        item = db.query(Item).get(o.item_id)
        view.append({
            "id": o.id,
            "title": item.title if item else "عنصر",
            "image": ("/" + item.image_path) if (item and item.image_path) else "/static/placeholder.svg",
            "start_date": o.start_date,
            "end_date": o.end_date,
            "days": o.days,
            "total": o.total_amount,
            "status": o.status
        })

    return request.app.templates.TemplateResponse(
        "my_orders.html",
        {"request": request, "title": "طلباتي", "session_user": u, "orders": view}
    )

@router.get("/payout/settings")
def payout_settings(request: Request):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "payout_settings.html",
        {"request": request, "title": "إعدادات التحويل", "session_user": u}
    )
