# app/routes_md_chatbot.py

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
router = APIRouter(prefix="/md/chatbot", tags=["md_chatbot"])


def _require_login(request: Request):
    return request.session.get("user")


def _ensure_md_session(db: Session, request: Request):
    sess = request.session.get("user")
    if not sess:
        return None

    # لو السيشن سبق وان وُسم كـ MD، استعمله مباشرة
    if sess.get("is_md", False):
        return sess

    # حمل المستخدم من الداتابيس
    u_db = db.query(User).filter(User.id == sess["id"]).first()
    if not u_db:
        return None

    # نعتبر الـ MD هو:
    # - مدير ديبو / مدفوعات
    #   أو
    # - أدمن عام في النظام
    is_md_role = bool(
        getattr(u_db, "is_deposit_manager", False)
        or getattr(u_db, "badge_admin", False)
    )

    if not is_md_role:
        return None

    # خزّن الفلاغ في السيشن حتى لا نعيد التحقق كل مرة
    sess["is_md"] = True
    request.session["user"] = sess
    return sess



# ================================
# MD INBOX
# ================================
@router.get("/inbox")
def md_chatbot_inbox(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/support/my", 303)

    base_q = db.query(SupportTicket).filter(
        SupportTicket.channel == "chatbot",
        SupportTicket.queue == "md_chatbot"
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
        "md_chatbot_inbox.html",
        {
            "request": request,
            "session_user": u_md,
            "title": "MD Chatbot Inbox",
            "data": data,
            "display_currency": display_currency,
        },
    )


# ================================
# VIEW TICKET
# ================================
@router.get("/ticket/{tid}")
def md_chatbot_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/support/my", 303)

    t = db.query(SupportTicket).filter(
        SupportTicket.id == tid,
        SupportTicket.channel == "chatbot",
        SupportTicket.queue == "md_chatbot"
    ).first()

    if not t:
        return RedirectResponse("/md/chatbot/inbox", 303)

    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "md_chatbot_ticket.html",
        {
            "request": request,
            "session_user": u_md,
            "ticket": t,
            "msgs": t.messages,
            "title": f"Chatbot Ticket #{t.id} (MD)",
            "display_currency": display_currency,
        },
    )


# ================================
# MD REPLY (FIRST CONTACT + REPLY)
# ================================
@router.post("/ticket/{tid}/reply")
def md_chatbot_reply(
    tid: int,
    request: Request,
    db: Session = Depends(get_db),
    body: str = Form("")
):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/support/my", 303)

    t = db.get(SupportTicket, tid)
    if not t or t.queue != "md_chatbot":
        return RedirectResponse("/md/chatbot/inbox", 303)

    now = datetime.utcnow()

    # -----------------------------------
    # 1) Send FIRST CONTACT message if not assigned
    # -----------------------------------
    if not t.assigned_to_id:
        first_contact = SupportMessage(
            ticket_id=t.id,
            sender_id=u_md["id"],
            sender_role="system",
            body=f"You are now chatting with one of our senior agents: {u_md['first_name']} {u_md['last_name']}.",
            created_at=now,
            channel="chatbot"
        )
        db.add(first_contact)
        t.assigned_to_id = u_md["id"]

    # -----------------------------------
    # 2) MD reply
    # -----------------------------------
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_md["id"],
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

    return RedirectResponse(f"/md/chatbot/ticket/{t.id}", 303)


# ================================
# RESOLVE
# ================================
@router.post("/tickets/{ticket_id}/resolve")
def md_chatbot_resolve(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", 303)

    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/support/my", 303)

    t = db.get(SupportTicket, ticket_id)
    if not t or t.queue != "md_chatbot":
        return RedirectResponse("/md/chatbot/inbox", 303)

    now = datetime.utcnow()

    t.status = "resolved"
    t.resolved_at = now
    t.updated_at = now
    if not t.assigned_to_id:
        t.assigned_to_id = u_md["id"]

    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_md["id"],
        sender_role="agent",
        body=f"MD resolved chatbot ticket at {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
        channel="chatbot"
    )
    db.add(msg)

    t.unread_for_user = True

    db.commit()
    return RedirectResponse("/md/chatbot/inbox", 303)
