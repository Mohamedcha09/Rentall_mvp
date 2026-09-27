"""Customer Support queue for the same SupportTicket used by /chatbot."""
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .database import get_db
from .models import SupportMessage, SupportTicket, User
from .support_ai import (
    AGENT_ACTIVE,
    add_agent_join_message,
    append_message,
    get_or_create_csrf_token,
    lock_agent_ticket_for_mutation,
    require_csrf,
    require_agent_assignment,
    update_ticket_summary,
    validate_message,
)
from .utils import display_currency


templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/cs/chatbot", tags=["cs_chatbot"])


def _require_login(request: Request):
    return request.session.get("user")


def _ensure_cs_session(db: Session, request: Request):
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None
    agent = db.get(User, uid)
    if not agent or not bool(getattr(agent, "is_support", False)):
        return None
    sess["is_support"] = True
    request.session["user"] = sess
    return sess


def _agent_from_session(db: Session, session: dict) -> User:
    agent = db.get(User, session.get("id"))
    if not agent or not bool(getattr(agent, "is_support", False)):
        raise HTTPException(status_code=403, detail="Not allowed")
    return agent


@router.get("/inbox")
def cs_chatbot_inbox(request: Request, db: Session = Depends(get_db)):
    session = _require_login(request)
    if not session:
        return RedirectResponse("/login", 303)
    session = _ensure_cs_session(db, request)
    if not session:
        return RedirectResponse("/support/my", 303)

    base = db.query(SupportTicket).filter(SupportTicket.channel == "chatbot", SupportTicket.queue == "cs_chatbot")
    data = {
        "new": base.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            SupportTicket.unread_for_agent.is_(True),
            SupportTicket.last_from == "user",
        ).order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at)).all(),
        "in_review": base.filter(
            SupportTicket.status == "open", SupportTicket.assigned_to_id.isnot(None)
        ).order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at)).all(),
        "resolved": base.filter(SupportTicket.status.in_(("resolved", "closed"))).order_by(
            desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at)
        ).all(),
    }
    return templates.TemplateResponse(
        request=request,
        name="cs_chatbot_inbox.html",
        context={"request": request, "session_user": session, "title": "CS Chatbot Inbox", "data": data, "display_currency": display_currency},
    )


@router.get("/ticket/{tid}")
def cs_chatbot_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    session = _require_login(request)
    if not session:
        return RedirectResponse("/login", 303)
    session = _ensure_cs_session(db, request)
    if not session:
        return RedirectResponse("/support/my", 303)
    ticket = db.query(SupportTicket).filter(
        SupportTicket.id == tid, SupportTicket.channel == "chatbot", SupportTicket.queue == "cs_chatbot"
    ).first()
    if not ticket:
        return RedirectResponse("/cs/chatbot/inbox", 303)
    agent = _agent_from_session(db, session)
    if ticket.assigned_to_id is not None:
        try:
            require_agent_assignment(ticket, agent)
        except HTTPException:
            return RedirectResponse("/cs/chatbot/inbox", 303)
    # A GET must not remove a queue item or alter assignment/read state.  The
    # successful, CSRF-protected claim/reply transition owns that mutation.
    return templates.TemplateResponse(
        request=request,
        name="cs_chatbot_ticket.html",
        context={
            "request": request,
            "session_user": session,
            "ticket": ticket,
            "msgs": ticket.messages,
            "support_summary": ticket.ai_summary or "No summary yet.",
            "csrf_token": get_or_create_csrf_token(request),
            "title": f"Chatbot Ticket #{ticket.id} (CS)",
            "display_currency": display_currency,
        },
    )


@router.post("/ticket/{tid}/reply")
def cs_chatbot_reply(
    tid: int,
    request: Request,
    body: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    session = _require_login(request)
    if not session:
        return RedirectResponse("/login", 303)
    session = _ensure_cs_session(db, request)
    if not session:
        return RedirectResponse("/support/my", 303)
    require_csrf(request, csrf_token)
    agent = _agent_from_session(db, session)
    cleaned = validate_message(body)
    try:
        ticket, newly_claimed = lock_agent_ticket_for_mutation(
            db,
            tid,
            agent,
            expected_queue="cs_chatbot",
            claim_if_waiting=True,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            return RedirectResponse("/cs/chatbot/inbox", 303)
        if exc.status_code == 409 and exc.detail == "Conversation is closed":
            return RedirectResponse(f"/cs/chatbot/ticket/{tid}", 303)
        raise
    if newly_claimed:
        add_agent_join_message(db, ticket, agent)
    append_message(db, ticket, agent, "agent", cleaned)
    now = datetime.utcnow()
    ticket.last_msg_at = now
    ticket.updated_at = now
    ticket.last_from = "agent"
    ticket.status = "open"
    ticket.ai_state = AGENT_ACTIVE
    ticket.unread_for_user = True
    ticket.unread_for_agent = False
    update_ticket_summary(db, ticket)
    db.commit()
    return RedirectResponse(f"/cs/chatbot/ticket/{ticket.id}", 303)
