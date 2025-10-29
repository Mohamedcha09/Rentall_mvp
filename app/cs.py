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

@router.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(ticket_id: int, db: Session = Depends(get_db)):
    t = db.get(SupportTicket, ticket_id)
    if t:
        t.status = "resolved"
        t.resolved_at = datetime.utcnow()
        t.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/cs/inbox", status_code=303)

@router.post("/tickets/{ticket_id}/assign_self")
def assign_self(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    t = db.get(SupportTicket, ticket_id)
    if t:
        t.assigned_to_id = user["id"]
        t.status = "open"
        t.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/cs/inbox", status_code=303)
