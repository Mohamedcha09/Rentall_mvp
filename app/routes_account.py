# app/routes_account.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from .database import get_db
from .models import (
    User, Item, Booking, ItemReview, Favorite, SupportTicket, MessageThread,
    Message, Rating, Report, ReportActionLog, Notification, FreezeDeposit,
    DepositAuditLog, DepositEvidence, Order, SupportMessage, UserReview
)

# نستخدم الـ templates مباشرة (بدون استيراد من main)
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["Account"])


# ================================
# 1) صفحة حذف الحساب
# ================================
@router.get("/account/delete")
def account_delete_page(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        "account_delete.html",
        {"request": request, "session_user": sess}
    )


# ================================
# 2) تأكيد حذف الحساب
# ================================
@router.post("/account/delete")
def account_delete_confirm(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse("/login", status_code=303)

    uid = sess["id"]

    # -------------------------
    # حذف جميع البيانات المرتبطة
    # -------------------------

    # رسائل & threads
    db.query(Message).filter(Message.sender_id == uid).delete()
    db.query(MessageThread).filter(
        (MessageThread.user_a_id == uid) |
        (MessageThread.user_b_id == uid)
    ).delete()

    # التقييمات
    db.query(Rating).filter(
        (Rating.rater_id == uid) |
        (Rating.rated_user_id == uid)
    ).delete()

    # المفضلات
    db.query(Favorite).filter(Favorite.user_id == uid).delete()

    # الحجوزات كمستأجر/مالك
    db.query(Booking).filter(
        (Booking.renter_id == uid) |
        (Booking.owner_id == uid)
    ).delete()

    # تجميد الودائع
    db.query(FreezeDeposit).filter(FreezeDeposit.user_id == uid).delete()

    # الطلبات
    db.query(Order).filter(
        (Order.renter_id == uid) |
        (Order.owner_id == uid)
    ).delete()

    # الأدلة & السجلات
    db.query(DepositEvidence).filter(DepositEvidence.uploader_id == uid).delete()
    db.query(DepositAuditLog).filter(DepositAuditLog.actor_id == uid).delete()

    # البلاغات
    db.query(ReportActionLog).filter(ReportActionLog.actor_id == uid).delete()
    db.query(Report).filter(Report.reporter_id == uid).delete()

    # تذاكر الدعم
    db.query(SupportMessage).filter(SupportMessage.sender_id == uid).delete()
    db.query(SupportTicket).filter(SupportTicket.user_id == uid).delete()

    # الإشعارات
    db.query(Notification).filter(Notification.user_id == uid).delete()

    # المراجعات
    db.query(ItemReview).filter(ItemReview.rater_id == uid).delete()
    db.query(UserReview).filter(
        (UserReview.owner_id == uid) |
        (UserReview.target_user_id == uid)
    ).delete()

    # العناصر
    db.query(Item).filter(Item.owner_id == uid).delete()

    # حذف المستخدم نفسه
    db.query(User).filter(User.id == uid).delete()

    db.commit()

    # حذف الجلسة + الكوكي
    request.session.clear()
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("ra_session")
    return resp
