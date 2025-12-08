# app/routes_mod_chatbot.py

from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .database import get_db
from .models import SupportTicket, SupportMessage, User
from .utils import display_currency

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/mod/chatbot", tags=["mod_chatbot"])


def _require_login(request: Request):
    return request.session.get("user")


def _ensure_mod_session(db: Session, request: Request):
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None
    if bool(sess.get("is_mod")):
        return sess

    u_db = db.get(User, uid)
    if u_db and bool(getattr(u_db, "is_mod", False)):
        sess["is_mod"] = True
        request.session["user"] = sess
        return sess

    return None


# ================================
# MOD CHATBOT INBOX
# ================================
@router.get("/inbox")
def mod_chatbot_inbox(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/support/my", 303)

    base_q = db.query(SupportTicket).filter(
        SupportTicket.channel == "chatbot",
        SupportTicket.queue == "mod_chatbot"   # ← FIXED
    )

    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            SupportTicket.last_from == "user",
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    in_review_q = (
        base_q.filter(
            SupportTicket.status == "open",
            SupportTicket.assigned_to_id.isnot(None),
        )
        .order_by(desc(SupportTicket.updated_at))
    )

    resolved_q = (
        base_q.filter(SupportTicket.status == "resolved")
        .order_by(desc(SupportTicket.resolved_at))
    )

    data = {
        "new": new_q.all(),
        "in_review": in_review_q.all(),
        "resolved": resolved_q.all(),
    }

    return templates.TemplateResponse(
        "mod_chatbot_inbox.html",
        {
            "request": request,
            "session_user": u_mod,
            "title": "MOD Chatbot Inbox",
            "data": data,
            "display_currency": display_currency,
        },
    )


# ================================
# VIEW TICKET
# ================================
@router.get("/ticket/{tid}")
def mod_chatbot_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/support/my", 303)

    t = db.query(SupportTicket).filter(
        SupportTicket.id == tid,
        SupportTicket.channel == "chatbot",
        SupportTicket.queue == "mod_chatbot"
    ).first()

    if not t:
        return RedirectResponse("/mod/chatbot/inbox", 303)

    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "mod_chatbot_ticket.html",
        {
            "request": request,
            "session_user": u_mod,
            "ticket": t,
            "msgs": t.messages,
            "title": f"Chatbot Ticket #{t.id} (MOD)",
            "display_currency": display_currency,
        },
    )


# ================================
# REPLY
# ================================
@router.post("/ticket/{tid}/reply")
def mod_chatbot_reply(tid: int, request: Request, db: Session = Depends(get_db), body: str = Form("")):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/support/my", 303)

    t = db.get(SupportTicket, tid)
    if not t or t.queue != "mod_chatbot":
        return RedirectResponse("/mod/chatbot/inbox", 303)

    now = datetime.utcnow()

    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="agent",
        body=(body or "").strip() or "(no text)",
        created_at=now,
        channel="chatbot"
    )
    db.add(msg)

    t.last_msg_at = now
    t.updated_at = now
    t.last_from = "agent"
    if not t.assigned_to_id:
        t.assigned_to_id = u_mod["id"]
    t.status = "open"
    t.unread_for_user = True
    t.unread_for_agent = False

    db.commit()

    return RedirectResponse(f"/mod/chatbot/ticket/{t.id}", 303)


# ================================
# RESOLVE
# ================================
@router.post("/tickets/{ticket_id}/resolve")
def mod_chatbot_resolve(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/support/my", 303)

    t = db.get(SupportTicket, ticket_id)
    if not t or t.queue != "mod_chatbot":
        return RedirectResponse("/mod/chatbot/inbox", 303)

    now = datetime.utcnow()

    t.status = "resolved"
    t.resolved_at = now
    t.updated_at = now
    if not t.assigned_to_id:
        t.assigned_to_id = u_mod["id"]

    m = SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="agent",
        body=f"MOD resolved chatbot ticket at {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
        channel="chatbot"
    )
    db.add(m)

    t.unread_for_user = True

    db.commit()
    return RedirectResponse("/mod/chatbot/inbox", 303)
