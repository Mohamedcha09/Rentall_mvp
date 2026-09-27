"""Management Desk view of the existing chatbot support queue."""
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .database import get_db
from .models import SupportTicket, User
from .support_ai import (
    AGENT_ACTIVE,
    RESOLVED,
    add_agent_join_message,
    append_message,
    get_or_create_csrf_token,
    lock_agent_ticket_for_mutation,
    require_agent_assignment,
    require_csrf,
    set_ticket_state,
    update_ticket_summary,
    validate_message,
)
from .utils import display_currency


templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/md/chatbot", tags=["md_chatbot"])


def _require_login(request: Request):
    return request.session.get("user")


def _ensure_md_session(db: Session, request: Request):
    session = request.session.get("user") or {}
    user = db.get(User, session.get("id")) if session.get("id") else None
    if not user or not bool(getattr(user, "is_deposit_manager", False) or getattr(user, "badge_admin", False)):
        return None
    session["is_md"] = True
    request.session["user"] = session
    return session


def _agent(db: Session, session: dict) -> User:
    user = db.get(User, session.get("id"))
    if not user or not bool(getattr(user, "is_deposit_manager", False) or getattr(user, "badge_admin", False)):
        raise HTTPException(status_code=403, detail="Not allowed")
    return user


@router.get("/inbox")
def md_chatbot_inbox(request: Request, db: Session = Depends(get_db)):
    session = _require_login(request)
    if not session:
        return RedirectResponse("/login", 303)
    session = _ensure_md_session(db, request)
    if not session:
        return RedirectResponse("/support/my", 303)
    base = db.query(SupportTicket).filter(SupportTicket.channel == "chatbot", SupportTicket.queue == "md_chatbot")
    data = {
        "new": base.filter(SupportTicket.assigned_to_id.is_(None), SupportTicket.status.in_(("new", "open")), SupportTicket.last_from == "user").order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at)).all(),
        "in_review": base.filter(SupportTicket.assigned_to_id.isnot(None), SupportTicket.status == "open").order_by(desc(SupportTicket.updated_at), desc(SupportTicket.last_msg_at)).all(),
        "resolved": base.filter(SupportTicket.status.in_(("resolved", "closed"))).order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at)).all(),
    }
    return templates.TemplateResponse(request=request, name="md_chatbot_inbox.html", context={"request": request, "session_user": session, "title": "MD Chatbot Inbox", "data": data, "display_currency": display_currency})


@router.get("/ticket/{tid}")
def md_chatbot_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    session = _require_login(request)
    if not session:
        return RedirectResponse("/login", 303)
    session = _ensure_md_session(db, request)
    if not session:
        return RedirectResponse("/support/my", 303)
    ticket = db.query(SupportTicket).filter(SupportTicket.id == tid, SupportTicket.channel == "chatbot", SupportTicket.queue == "md_chatbot").first()
    if not ticket:
        return RedirectResponse("/md/chatbot/inbox", 303)
    agent = _agent(db, session)
    if ticket.assigned_to_id is not None:
        try:
            require_agent_assignment(ticket, agent)
        except HTTPException:
            return RedirectResponse("/md/chatbot/inbox", 303)
    # Keep ticket views read-only: merely following a link must not hide a
    # waiting conversation from the queue.
    return templates.TemplateResponse(request=request, name="md_chatbot_ticket.html", context={"request": request, "session_user": session, "ticket": ticket, "msgs": ticket.messages, "support_summary": ticket.ai_summary or "No summary yet.", "csrf_token": get_or_create_csrf_token(request), "title": f"Chatbot Ticket #{ticket.id} (MD)", "display_currency": display_currency})


@router.post("/ticket/{tid}/reply")
def md_chatbot_reply(tid: int, request: Request, body: str = Form(""), csrf_token: str = Form(""), db: Session = Depends(get_db)):
    session = _require_login(request)
    if not session:
        return RedirectResponse("/login", 303)
    session = _ensure_md_session(db, request)
    if not session:
        return RedirectResponse("/support/my", 303)
    require_csrf(request, csrf_token)
    agent = _agent(db, session)
    cleaned = validate_message(body)
    try:
        ticket, newly_claimed = lock_agent_ticket_for_mutation(
            db,
            tid,
            agent,
            expected_queue="md_chatbot",
            claim_if_waiting=True,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            return RedirectResponse("/md/chatbot/inbox", 303)
        if exc.status_code == 409 and exc.detail == "Conversation is closed":
            return RedirectResponse(f"/md/chatbot/ticket/{tid}", 303)
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
    return RedirectResponse(f"/md/chatbot/ticket/{ticket.id}", 303)


@router.post("/tickets/{ticket_id}/resolve")
def md_chatbot_resolve(ticket_id: int, request: Request, csrf_token: str = Form(""), db: Session = Depends(get_db)):
    session = _require_login(request)
    if not session:
        return RedirectResponse("/login", 303)
    session = _ensure_md_session(db, request)
    if not session:
        return RedirectResponse("/support/my", 303)
    require_csrf(request, csrf_token)
    agent = _agent(db, session)
    try:
        ticket, _ = lock_agent_ticket_for_mutation(
            db,
            ticket_id,
            agent,
            expected_queue="md_chatbot",
            claim_if_waiting=True,
        )
    except HTTPException as exc:
        if exc.status_code in {404, 409}:
            return RedirectResponse("/md/chatbot/inbox", 303)
        raise
    now = datetime.utcnow()
    ticket.status = "resolved"
    ticket.resolved_at = now
    ticket.updated_at = now
    set_ticket_state(ticket, RESOLVED)
    ticket.last_from = "agent"
    ticket.unread_for_user = True
    ticket.unread_for_agent = False
    append_message(db, ticket, agent, "system", "This conversation has been resolved by Sevor Management Desk.", metadata={"event": "resolved_by_agent"})
    update_ticket_summary(db, ticket)
    db.commit()
    return RedirectResponse("/md/chatbot/inbox", 303)
