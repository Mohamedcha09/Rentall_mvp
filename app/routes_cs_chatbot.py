# app/routes_cs_chatbot.py

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
router = APIRouter(prefix="/cs/chatbot", tags=["cs_chatbot"])


# ------------------------------------------------
# HELPERS
# ------------------------------------------------

def _require_login(request: Request):
    return request.session.get("user")


def _ensure_cs_session(db: Session, request: Request):
    """
    Vérifie que l'utilisateur est agent CS (customer support).
    """
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None

    if bool(sess.get("is_support", False)):
        return sess

    u_db = db.get(User, uid)
    if u_db and bool(getattr(u_db, "is_support", False)):
        sess["is_support"] = True
        request.session["user"] = sess
        return sess

    return None


# ------------------------------------------------
# INBOX (CS CHATBOT)
# ------------------------------------------------

@router.get("/inbox")
def cs_chatbot_inbox(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", 303)

    base_q = db.query(SupportTicket).filter(
        SupportTicket.channel == "chatbot",
        SupportTicket.queue == "cs_chatbot"
    )

    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            SupportTicket.unread_for_agent.is_(True),
            SupportTicket.last_from == "user",
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    in_review_q = (
        base_q.filter(
            SupportTicket.status == "open",
            SupportTicket.assigned_to_id.isnot(None),
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
    )

    resolved_q = (
        base_q.filter(SupportTicket.status == "resolved")
        .order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at))
    )

    data = {
        "new": new_q.all(),
        "in_review": in_review_q.all(),
        "resolved": resolved_q.all(),
    }

    return templates.TemplateResponse(
        "cs_chatbot_inbox.html",
        {
            "request": request,
            "session_user": u_cs,
            "title": "CS Chatbot Inbox",
            "data": data,
            "display_currency": display_currency,
        },
    )


# ------------------------------------------------
# VIEW TICKET  ✅ FIX: ASSIGN ON OPEN + INTRO MESSAGE
# ------------------------------------------------

@router.get("/ticket/{tid}")
def cs_chatbot_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", 303)

    t = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.id == tid,
            SupportTicket.channel == "chatbot",
            SupportTicket.queue == "cs_chatbot",
        )
        .first()
    )

    if not t:
        return RedirectResponse("/cs/chatbot/inbox", 303)

    now = datetime.utcnow()

    # ✅ CRITICAL: mark ticket assigned as soon as CS OPENS it
    if not t.assigned_to_id:
        t.assigned_to_id = u_cs["id"]

        agent_name = (
            f"{(u_cs.get('first_name') or '').strip()} {(u_cs.get('last_name') or '').strip()}".strip()
            or (u_cs.get("email") or "Support agent")
        )

        db.add(SupportMessage(
            ticket_id=t.id,
            sender_id=u_cs["id"],
            sender_role="agent",  # مهم: الواجهة تعتبره Agent
            body=f"You're now connected with {agent_name}. How can I help you?",
            created_at=now,
            channel="chatbot",
        ))

        t.last_from = "agent"
        t.status = "open"
        t.unread_for_user = True
        t.updated_at = now
        t.last_msg_at = now

    # Mark as read for agent
    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "cs_chatbot_ticket.html",
        {
            "request": request,
            "session_user": u_cs,
            "ticket": t,
            "msgs": t.messages,
            "title": f"Chatbot Ticket #{t.id} (CS)",
            "display_currency": display_currency,
        },
    )


# ------------------------------------------------
# REPLY
# ------------------------------------------------

@router.post("/ticket/{tid}/reply")
def cs_chatbot_reply(
    tid: int,
    request: Request,
    db: Session = Depends(get_db),
    body: str = Form("")
):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", 303)

    t = db.get(SupportTicket, tid)
    if not t or t.queue != "cs_chatbot":
        return RedirectResponse("/cs/chatbot/inbox", 303)

    now = datetime.utcnow()

    # If still not assigned (rare), assign here too (no duplicate intro because view already did it)
    if not t.assigned_to_id:
        t.assigned_to_id = u_cs["id"]

    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_cs["id"],
        sender_role="agent",
        body=(body or "").strip() or "(no text)",
        created_at=now,
        channel="chatbot"
    )
    db.add(msg)

    t.last_msg_at = now
    t.updated_at = now
    t.last_from = "agent"
    t.status = "open"
    t.unread_for_user = True
    t.unread_for_agent = False

    db.commit()

    return RedirectResponse(f"/cs/chatbot/ticket/{t.id}", 303)
