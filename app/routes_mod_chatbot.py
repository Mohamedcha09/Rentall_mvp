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


# ------------------------------------------------
# HELPERS
# ------------------------------------------------

def _require_login(request: Request):
    return request.session.get("user")


def _ensure_mod_session(db: Session, request: Request):
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None

    # already validated once
    if sess.get("is_mod", False):
        return sess

    # reload from DB
    u = db.get(User, uid)
    if u and bool(getattr(u, "is_mod", False)):
        sess["is_mod"] = True
        request.session["user"] = sess
        return sess

    return None


# ------------------------------------------------
# 📥 MOD INBOX — FINAL VERSION
# ------------------------------------------------

@router.get("/inbox")
def mod_chatbot_inbox(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/support/my", 303)

    base = db.query(SupportTicket).filter(
        SupportTicket.channel == "chatbot",
        SupportTicket.queue == "mod_chatbot"
    )

    # -----------------------------
    # 🆕 NEW
    # -----------------------------
    new_q = base.filter(
        SupportTicket.assigned_to_id.is_(None),
        SupportTicket.status.in_(("new", "open")),
        SupportTicket.last_from == "user",
    ).order_by(
        desc(SupportTicket.last_msg_at),
        desc(SupportTicket.created_at)
    )

    # -----------------------------
    # 📂 IN REVIEW
    # -----------------------------
    in_review_q = base.filter(
        SupportTicket.assigned_to_id.isnot(None),
        SupportTicket.status == "open",
    ).order_by(
        desc(SupportTicket.updated_at),
        desc(SupportTicket.last_msg_at)
    )

    # -----------------------------
    # ✅ RESOLVED
    # -----------------------------
    resolved_q = base.filter(
            SupportTicket.status.in_(("resolved", "closed"))
    ).order_by(
        desc(SupportTicket.resolved_at),
        desc(SupportTicket.updated_at)
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


# ------------------------------------------------
# VIEW TICKET
# ------------------------------------------------

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

    # mark as read for agent
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


# ------------------------------------------------
# REPLY (FIRST CONTACT + NORMAL REPLY)
# ------------------------------------------------

@router.post("/ticket/{tid}/reply")
def mod_chatbot_reply(
    tid: int,
    request: Request,
    db: Session = Depends(get_db),
    body: str = Form("")
):
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

    # FIRST CONTACT
    if not t.assigned_to_id:
        intro = SupportMessage(
            ticket_id=t.id,
            sender_id=u_mod["id"],
            sender_role="system",
            body=f"You are now chatting with one of our moderation specialists: {u_mod['first_name']} {u_mod['last_name']}.",
            created_at=now,
            channel="chatbot"
        )
        db.add(intro)
        t.assigned_to_id = u_mod["id"]

    # REAL REPLY
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="agent",
        body=(body or "").trim() if hasattr(body, "trim") else (body.strip() or "(no text)"),
        created_at=now,
        channel="chatbot"
    )
    db.add(msg)

    # update ticket
    t.last_msg_at = now
    t.updated_at = now
    t.last_from = "agent"
    t.status = "open"
    t.unread_for_user = True
    t.unread_for_agent = False

    db.commit()

    return RedirectResponse(f"/mod/chatbot/ticket/{t.id}", 303)


# ------------------------------------------------
# RESOLVE
# ------------------------------------------------

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

    close_msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="agent",
        body=f"MOD resolved chatbot ticket at {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
        channel="chatbot"
    )
    db.add(close_msg)

    t.unread_for_user = True

    db.commit()

    return RedirectResponse("/mod/chatbot/inbox", 303)
