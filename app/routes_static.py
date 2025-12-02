from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .utils import display_currency

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["static-pages"])

def get_session_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)

@router.get("/delete-account", include_in_schema=False)
def delete_account_page(
    request: Request,
    db: Session = Depends(get_db)
):
    session_user = get_session_user(request, db)

    return templates.TemplateResponse(
        "delete_account.html",
        {
            "request": request,
            "session_user": session_user,
            "display_currency": display_currency
        }
    )
