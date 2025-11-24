# app/routes_account.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Item, Booking, ItemReview, Favorite, SupportTicket
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

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

    user_id = sess["id"]

    # حذف بيانات المستخدم بالكامل
    db.query(Item).filter(Item.owner_id == user_id).delete()
    db.query(Booking).filter(
        (Booking.owner_id == user_id) |
        (Booking.renter_id == user_id)
    ).delete()
    db.query(ItemReview).filter(ItemReview.user_id == user_id).delete()
    db.query(Favorite).filter(Favorite.user_id == user_id).delete()
    db.query(SupportTicket).filter(SupportTicket.user_id == user_id).delete()

    # حذف حساب المستخدم
    db.query(User).filter(User.id == user_id).delete()

    db.commit()

    # مسح الجلسة والخروج
    request.session.clear()
    resp = RedirectResponse("/", status_code=303)
    try:
        resp.delete_cookie("session")
    except:
        pass

    return resp
