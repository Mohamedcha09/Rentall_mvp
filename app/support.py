# app/support.py
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import SupportTicket, SupportMessage, User

# ✅ import internal notifications function
from .notifications_api import push_notification

router = APIRouter()


# ===== Helpers =====
def _require_login(request: Request):
    u = request.session.get("user")
    if not u:
        return None
    return u

def bump_ticket_on_message(db, ticket_id, author_user, is_cs_author: bool):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        return
    t.last_msg_at = datetime.utcnow()
    t.updated_at = datetime.utcnow()

    if is_cs_author:
        # last message from support
        t.last_from = "agent"
        # confirm assignment + keep it open
        if not t.assigned_to_id:
            t.assigned_to_id = author_user.id
        if t.status in (None, "new", "resolved"):
            t.status = "open"
        # read by agent now
        t.unread_for_agent = False
        # mark as unread for user so they will see the reply
        t.unread_for_user = True
    else:
        # last message from the customer
        t.last_from = "user"
        # if closed, reopen it
        if t.status == "resolved":
            t.status = "open"
        # became unread for agent
        t.unread_for_agent = True

    db.commit()


def _ensure_cs_session(db: Session, request: Request):
    """
    ✅ Used as a smart "fallback":
    - If the session does not have is_support=True but the user in DB has become CS,
      update the session immediately within the same request and return the updated session_user.
    - If not logged in or not actually CS, return None.
    """
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None

    # if session already has is_support=True, return it as-is
    if bool(sess.get("is_support", False)):
        return sess

    # old session? verify with DB
    u_db = db.get(User, uid)
    if u_db and bool(getattr(u_db, "is_support", False)):
        # update session in the same request then return it
        sess["is_support"] = True
        request.session["user"] = sess
        return sess

    # not actually CS
    return None


# ✅ function to notify all CS agents when a new ticket is opened
def _notify_support_agents_on_new_ticket(db: Session, ticket: SupportTicket):
    agents = (
        db.query(User)
        .filter(User.is_support == True, User.status == "approved")
        .all()
    )
    # you can keep the direct ticket link or make it /cs/inbox per team preference
    url = f"/cs/ticket/{ticket.id}"
    title = "🎫 New support ticket"
    body = f"#{ticket.id} — {ticket.subject or ''}".strip()

    for ag in agents:
        try:
            push_notification(
                db,
                ag.id,
                title,
                body,
                url,
                "support",  # notification kind
            )
        except Exception:
            # do not block ticket creation if one notification fails
            pass


# ========== Customer UI ==========

@router.get("/support/new", response_class=HTMLResponse)
def support_new(request: Request):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "support_new.html",
        {"request": request, "session_user": u, "title": "Contact Support"},
    )


@router.post("/support/new")
def support_new_post(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    # Starlette stores the last form in request._form — provide a safe fallback if unavailable
    form = getattr(request, "_form", None)
    if form is None:
        import anyio

        async def _read_form():
            return await request.form()

        form = anyio.from_thread.run(_read_form)

    subject = form.get("subject", "").strip() if form else ""
    body = form.get("body", "").strip() if form else ""

    if not subject:
        subject = "No subject"

    # create ticket + first message
    t = SupportTicket(
        user_id=u["id"],
        subject=subject,
        status="new",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        last_from="user",
        unread_for_agent=True,
        unread_for_user=False,
    )
    db.add(t)
    db.flush()

    m = SupportMessage(
        ticket_id=t.id,
        sender_id=u["id"],
        sender_role="user",
        body=body or "(no text)",
        created_at=datetime.utcnow(),
    )
    db.add(m)
    db.commit()

    # ✅ after successful creation: notify CS agents
    _notify_support_agents_on_new_ticket(db, t)

    return RedirectResponse("/support/my", status_code=303)


@router.get("/support/my", response_class=HTMLResponse)
def support_my(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    # ✅ نعرض فقط تذاكر السيبور القديم
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == u["id"])
        .filter((SupportTicket.channel == None) | (SupportTicket.channel != "chatbot"))
        .order_by(SupportTicket.updated_at.desc())
        .all()
    )

    return request.app.templates.TemplateResponse(
        "support_my.html",
        {
            "request": request,
            "session_user": u,
            "tickets": tickets,
            "title": "My Tickets",
        },
    )


@router.get("/support/ticket/{tid}", response_class=HTMLResponse)
def support_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not t or t.user_id != u["id"]:
        return RedirectResponse("/support/my", status_code=303)

    # mark agent messages as read + reset "unread for user" flag
    for msg in t.messages or []:
        if msg.sender_role == "agent" and not getattr(msg, "is_read", False):
            msg.is_read = True
    t.unread_for_user = False
    db.commit()

    return request.app.templates.TemplateResponse(
        "support_ticket.html",
        {
            "request": request,
            "session_user": u,
            "ticket": t,
            "msgs": t.messages,
            "title": f"Ticket #{t.id}",
        },
    )



@router.post("/support/ticket/{tid}/reply")
def support_ticket_reply(tid: int, request: Request, db: Session = Depends(get_db), body: str = Form("")):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    t = db.get(SupportTicket, tid)
    if not t or t.user_id != u["id"]:
        return RedirectResponse("/support/my", status_code=303)

    # create a customer message
    m = SupportMessage(
        ticket_id=t.id,
        sender_id=u["id"],
        sender_role="user",
        body=(body or "").strip() or "(no text)",
        created_at=datetime.utcnow(),
    )
    db.add(m)

    # update ticket state and flags
    t.last_msg_at = datetime.utcnow()
    t.updated_at = datetime.utcnow()
    t.last_from = "user"
    if t.status == "resolved":
        t.status = "open"
    t.unread_for_agent = True
    t.unread_for_user = False
    db.commit()

    # notify the assigned agent if any, otherwise all approved CS staff
    if t.assigned_to_id:
        push_notification(
            db,
            t.assigned_to_id,
            "💬 New customer reply",
            f"#{t.id} — {t.subject or ''}",
            url=f"/cs/ticket/{t.id}",
            kind="support",
        )
    else:
        agents = db.query(User).filter(User.is_support==True, User.status=="approved").all()
        for ag in agents:
            push_notification(
                db,
                ag.id,
                "💬 New customer reply",
                f"#{t.id} — {t.subject or ''}",
                url=f"/cs/ticket/{t.id}",
                kind="support",
            )

    return RedirectResponse(f"/support/ticket/{t.id}", status_code=303)
