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

    # Si déjà support dans la session → ok
    if bool(sess.get("is_support", False)):
        return sess

    # Sinon reload depuis DB
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

    # Nouveaux tickets
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            SupportTicket.unread_for_agent.is_(True),
            SupportTicket.last_from == "user",
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    # Tickets en cours (assignés)
    in_review_q = (
        base_q.filter(
            SupportTicket.status == "open",
            SupportTicket.assigned_to_id.isnot(None),
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
    )

    # Tickets résolus
    resolved_q = (
        base_q.filter(SupportTicket.status.in_(("resolved", "closed")))
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
# VIEW TICKET (CORRIGÉ → tid: int)
# ------------------------------------------------

@router.get("/ticket/{tid}")
def cs_chatbot_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", 303)

    # IMPORTANT: tid est maintenant int, pas string
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

    # Marquer comme lu pour agent
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
# REPLY (AVEC MESSAGE D’ACCUEIL LA PREMIÈRE FOIS)
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

    # =================================================
    # 1) FIRST AGENT CONTACT (CRITICAL)
    # =================================================
    if not t.assigned_to_id:
        t.assigned_to_id = u_cs["id"]

        first_contact = SupportMessage(
            ticket_id=t.id,
            sender_id=u_cs["id"],
            sender_role="agent",  # ⭐ مهم جداً
            body=f"You're now connected with {u_cs['first_name']} {u_cs['last_name']}. How can I help you?",
            created_at=now,
            channel="chatbot"
        )
        db.add(first_contact)

    # =================================================
    # 2) AGENT REPLY
    # =================================================
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_cs["id"],
        sender_role="agent",
        body=(body or "").strip() or "(no text)",
        created_at=now,
        channel="chatbot"
    )
    db.add(msg)

    # =================================================
    # 3) UPDATE TICKET
    # =================================================
    t.last_msg_at = now
    t.updated_at = now
    t.last_from = "agent"
    t.status = "open"
    t.unread_for_user = True
    t.unread_for_agent = False

    db.commit()

    return RedirectResponse(f"/cs/chatbot/ticket/{t.id}", 303)
