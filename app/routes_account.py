# app/routes_account.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_

from .database import get_db
from .models import (
    User, Item, Booking, ItemReview, Favorite, SupportTicket, MessageThread,
    Message, MessageAttachment, Rating, Report, ReportActionLog, Notification, FreezeDeposit,
    DepositAuditLog, DepositEvidence, Order, SupportMessage, SupportAttachment,
    SupportMessageReceipt, UserReview, FinderConversation, FinderMessage,
    FinderSearchState, FinderListingIndex
)
from .support_attachments import remove_saved_attachment_files
from .message_attachments import (
    message_attachment_cleanup_reference,
    remove_saved_message_attachment_files,
)
from .models_metrics import OnlineSession

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
        request=request,
        name="account_delete.html",
        context={"request": request, "session_user": sess},
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

    # Direct messages.  Collect every participating thread first: deleting an
    # account deletes its private conversations, so attachment rows/files from
    # either participant in those threads must go with the thread.
    direct_thread_ids = [
        row[0]
        for row in db.query(MessageThread.id).filter(
            (MessageThread.user_a_id == uid) |
            (MessageThread.user_b_id == uid)
        ).all()
    ]
    direct_attachment_scope = (
        or_(MessageAttachment.thread_id.in_(direct_thread_ids), MessageAttachment.uploader_id == uid)
        if direct_thread_ids
        else (MessageAttachment.uploader_id == uid)
    )
    direct_attachments = db.query(MessageAttachment).filter(direct_attachment_scope).all()
    direct_attachment_cleanup = [
        message_attachment_cleanup_reference(attachment)
        for attachment in direct_attachments
    ]
    db.query(MessageAttachment).filter(direct_attachment_scope).delete(synchronize_session=False)
    if direct_thread_ids:
        db.query(Message).filter(Message.thread_id.in_(direct_thread_ids)).delete(synchronize_session=False)
    else:
        db.query(Message).filter(Message.sender_id == uid).delete(synchronize_session=False)
    db.query(MessageThread).filter(
        (MessageThread.user_a_id == uid) |
        (MessageThread.user_b_id == uid)
    ).delete(synchronize_session=False)

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

    # تذاكر الدعم.  Their attachments are private files outside the public
    # uploads mount, so collect them before the relational cleanup and remove
    # their physical bytes only after the database transaction succeeds.
    owned_ticket_ids = [
        row[0]
        for row in db.query(SupportTicket.id).filter(SupportTicket.user_id == uid).all()
    ]
    ticket_or_sender = (
        or_(SupportMessage.ticket_id.in_(owned_ticket_ids), SupportMessage.sender_id == uid)
        if owned_ticket_ids
        else (SupportMessage.sender_id == uid)
    )
    attachment_ticket_or_uploader = (
        or_(SupportAttachment.ticket_id.in_(owned_ticket_ids), SupportAttachment.uploader_id == uid)
        if owned_ticket_ids
        else (SupportAttachment.uploader_id == uid)
    )
    support_attachments = db.query(SupportAttachment).filter(attachment_ticket_or_uploader).all()
    private_attachment_names = [attachment.stored_name for attachment in support_attachments]
    support_message_ids = [
        row[0]
        for row in db.query(SupportMessage.id)
        .filter(ticket_or_sender)
        .all()
    ]
    if support_message_ids:
        db.query(SupportMessageReceipt).filter(
            or_(
                SupportMessageReceipt.message_id.in_(support_message_ids),
                SupportMessageReceipt.reader_id == uid,
            )
        ).delete(synchronize_session=False)
    else:
        db.query(SupportMessageReceipt).filter(
            SupportMessageReceipt.reader_id == uid
        ).delete(synchronize_session=False)
    db.query(SupportAttachment).filter(attachment_ticket_or_uploader).delete(synchronize_session=False)
    db.query(SupportMessage).filter(ticket_or_sender).delete(synchronize_session=False)
    db.query(SupportTicket).filter(SupportTicket.user_id == uid).delete(synchronize_session=False)

    # Finder is deliberately independent from Support/direct messages, so its
    # small conversation tree must be removed explicitly before the account.
    # The listing index is derived data and must also be removed before bulk
    # deleting owned Items on databases that enforce foreign keys.
    finder_conversation_ids = [
        row[0]
        for row in db.query(FinderConversation.id)
        .filter(FinderConversation.user_id == uid)
        .all()
    ]
    if finder_conversation_ids:
        db.query(FinderMessage).filter(
            FinderMessage.conversation_id.in_(finder_conversation_ids)
        ).delete(synchronize_session=False)
        db.query(FinderSearchState).filter(
            FinderSearchState.conversation_id.in_(finder_conversation_ids)
        ).delete(synchronize_session=False)
        db.query(FinderConversation).filter(
            FinderConversation.id.in_(finder_conversation_ids)
        ).delete(synchronize_session=False)
    owned_item_ids = [
        row[0]
        for row in db.query(Item.id).filter(Item.owner_id == uid).all()
    ]
    if owned_item_ids:
        db.query(FinderListingIndex).filter(
            FinderListingIndex.item_id.in_(owned_item_ids)
        ).delete(synchronize_session=False)

    # الإشعارات
    db.query(Notification).filter(Notification.user_id == uid).delete()

    # Presence sessions are not FK-bound.  Remove them so an account that was
    # deleted cannot remain visible as recently online if its id is reused.
    db.query(OnlineSession).filter(OnlineSession.user_id == uid).delete(synchronize_session=False)

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
    remove_saved_attachment_files(private_attachment_names)
    remove_saved_message_attachment_files(direct_attachment_cleanup)

    # حذف الجلسة + الكوكي
    request.session.clear()
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("ra_session")
    return resp
