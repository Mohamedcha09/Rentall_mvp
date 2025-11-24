# app/routes_account.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    User, Item, Booking, ItemReview, Favorite, SupportTicket, MessageThread,
    Message, Rating, Report, ReportActionLog, Notification, FreezeDeposit,
    DepositAuditLog, DepositEvidence, Order, SupportMessage, UserReview
)

# استخدم نفس templates الخاصة بالموقع (مهم جداً)
from app.main import templates

router = APIRouter(tags=["Account"])

@router.get("/account/delete")
def delete_page(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        "account_delete.html",
        {"request": request, "session_user": sess}
    )

@router.post("/account/delete")
def delete_confirm(request: Request, db: Session = Depends(get_db)):
    sess = request.session.get("user")
    if not sess:
        return RedirectResponse("/login", status_code=303)

    uid = sess["id"]

    # حذف الرسائل والـ threads
    db.query(Message).filter(Message.sender_id == uid).delete()
    db.query(MessageThread).filter(
        (MessageThread.user_a_id == uid) |
        (MessageThread.user_b_id == uid)
    ).delete()

    # حذف التقييمات
    db.query(Rating).filter(
        (Rating.rater_id == uid) |
        (Rating.rated_user_id == uid)
    ).delete()

    # حذف المفضلات
    db.query(Favorite).filter(Favorite.user_id == uid).delete()

    # حذف bookings (كمستأجر/كمالك)
    db.query(Booking).filter(
        (Booking.renter_id == uid) |
        (Booking.owner_id == uid)
    ).delete()

    # Freeze deposits
    db.query(FreezeDeposit).filter(FreezeDeposit.user_id == uid).delete()

    # Orders
    db.query(Order).filter(
        (Order.renter_id == uid) |
        (Order.owner_id == uid)
    ).delete()

    # Deposit audit logs + Evidence
    db.query(DepositEvidence).filter(DepositEvidence.uploader_id == uid).delete()
    db.query(DepositAuditLog).filter(DepositAuditLog.actor_id == uid).delete()

    # Reports
    db.query(ReportActionLog).filter(ReportActionLog.actor_id == uid).delete()
    db.query(Report).filter(Report.reporter_id == uid).delete()

    # Support Tickets + messages
    db.query(SupportMessage).filter(SupportMessage.sender_id == uid).delete()
    db.query(SupportTicket).filter(SupportTicket.user_id == uid).delete()

    # Notifications
    db.query(Notification).filter(Notification.user_id == uid).delete()

    # Reviews (item reviews + user reviews)
    db.query(ItemReview).filter(ItemReview.rater_id == uid).delete()
    db.query(UserReview).filter(
        (UserReview.owner_id == uid) |
        (UserReview.target_user_id == uid)
    ).delete()

    # حذف جميع الـ Items الخاصة به
    db.query(Item).filter(Item.owner_id == uid).delete()

    # حذف المستخدم نفسه
    db.query(User).filter(User.id == uid).delete()

    db.commit()

    # حذف الجلسة
    request.session.clear()
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session")
    return resp
