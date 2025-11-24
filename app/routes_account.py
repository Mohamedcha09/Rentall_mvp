# app/routes_account.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Item, Booking, ItemReview, Favorite, SupportTicket
from .auth_utils import get_current_user  # عدلها حسب مشروعك
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["Account"])
@router.get("/account/delete")
def account_delete_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    return templates.TemplateResponse(
        "account_delete.html",
        {"request": request, "user": user}
    )

@router.post("/account/delete")
def account_delete_confirm(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    # حذف items
    db.query(Item).filter(Item.owner_id == user.id).delete()

    # حذف bookings
    db.query(Booking).filter(
        (Booking.owner_id == user.id) | (Booking.renter_id == user.id)
    ).delete()

    # حذف reviews
    db.query(ItemReview).filter(ItemReview.user_id == user.id).delete()

    # حذف favorites
    db.query(Favorite).filter(Favorite.user_id == user.id).delete()

    # حذف tickets
    db.query(SupportTicket).filter(SupportTicket.user_id == user.id).delete()

    # حذف المستخدم نفسه
    db.delete(user)

    db.commit()

    # تسجيل الخروج
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("session")
    return response
