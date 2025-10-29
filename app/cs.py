# app/cs.py
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .database import get_db
from .models import SupportTicket

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/cs", tags=["cs"])

@router.get("/inbox")
def cs_inbox(request: Request, db: Session = Depends(get_db)):
    base_q = db.query(SupportTicket)

    data = {
        "new": base_q.filter(SupportTicket.status == "new")
                     .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
                     .all(),
        "in_review": base_q.filter(SupportTicket.status == "open")
                     .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
                     .all(),
        "resolved": base_q.filter(SupportTicket.status == "resolved")
                     .order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at))
                     .all(),
    }

    return templates.TemplateResponse(
        "cs_inbox.html",
        {
            "request": request,
            "title": "CS Inbox",
            "data": data
        }
    )

