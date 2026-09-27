# app/cs.py
from datetime import datetime
from fastapi import APIRouter, Request, Depends, File, Form, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, text

from .database import get_db
from .models import SupportTicket, SupportMessage, User
from .notifications_api import push_notification, notify_mods, notify_dms
from .support import (
    create_legacy_support_message,
    mark_legacy_ticket_messages_read,
    staff_can_view_legacy_ticket,
)
from .support_ai import get_or_create_csrf_token, require_csrf
from .support_attachments import allowed_accept_value, max_attachment_bytes
from .utils import display_currency   # ← ★★★ مهم جداً

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/cs", tags=["cs"])


# ---------------------------
# Helpers
# ---------------------------
def _require_login(request: Request):
    return request.session.get("user")


def _ensure_cs_session(db: Session, request: Request):
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None
    if bool(sess.get("is_support")):
        return sess
    u_db = db.get(User, uid)
    if u_db and bool(getattr(u_db, "is_support", False)):
        sess["is_support"] = True
        request.session["user"] = sess
        return sess
    return None


def _is_legacy_ticket(ticket: SupportTicket | None) -> bool:
    """Keep the old CS UI from bypassing chatbot queue/state authorization."""
    return bool(ticket and getattr(ticket, "channel", None) != "chatbot")


# ---------------------------
# CS Inbox
# ---------------------------
@router.get("/inbox")
def cs_inbox(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    base_q = db.query(SupportTicket).filter(
        text("COALESCE(queue,'cs') = 'cs'"),
        (SupportTicket.channel == None) | (SupportTicket.channel != "chatbot"),
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
        request=request,
        name="cs_inbox.html",
        context={
            "request": request,
            "session_user": u_cs,
            "title": "CS Inbox",
            "data": data,
            "display_currency": display_currency,  # ← ★★ إضافة مهمة
        },
    )


# ---------------------------
# View Ticket
# ---------------------------
@router.get("/ticket/{tid}")
def cs_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not _is_legacy_ticket(t):
        return RedirectResponse("/cs/inbox", status_code=303)

    # Direct URLs must still respect the legacy queue boundary.  This is the
    # same authorization rule used before serving a private attachment.
    staff_user = db.get(User, u_cs["id"])
    if not staff_user or not staff_can_view_legacy_ticket(t, staff_user):
        return RedirectResponse("/cs/inbox", status_code=303)

    # A read receipt is written only after a real, authorized staff view.
    # The helper also keeps the legacy unread flag in sync for the inbox.
    mark_legacy_ticket_messages_read(
        db,
        ticket=t,
        reader=staff_user,
        reader_role="agent",
    )

    return templates.TemplateResponse(
        request=request,
        name="cs_ticket.html",
        context={
            "request": request,
            "session_user": u_cs,
            "ticket": t,
            "msgs": t.messages,
            "title": f"Ticket #{t.id} (CS)",
            "display_currency": display_currency,  # ← هنا أيضاً
            "csrf_token": get_or_create_csrf_token(request),
            "attachment_accept": allowed_accept_value(),
            "max_attachment_bytes": max_attachment_bytes(),
        },
    )


# ---------------------------
# Assign Self
# ---------------------------
@router.post("/tickets/{ticket_id}/assign_self")
def cs_assign_self(
    ticket_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if not _is_legacy_ticket(t):
        return RedirectResponse("/cs/inbox", status_code=303)
    if str(t.status or "").lower() == "closed":
        return RedirectResponse(f"/cs/ticket/{ticket_id}", status_code=303)
    row = db.execute(
        text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"),
        {"tid": ticket_id},
    ).first()
    # ``cs_chatbot`` is accepted only as a compatibility value on a *legacy*
    # row; the legacy guard above keeps actual chatbot tickets out.
    if not row or (row[0] or "cs") not in {"cs", "cs_chatbot"}:
        return RedirectResponse("/cs/inbox", status_code=303)
    staff_user = db.get(User, u_cs["id"])
    if not staff_user or not staff_can_view_legacy_ticket(t, staff_user):
        return RedirectResponse("/cs/inbox", status_code=303)
    require_csrf(request, csrf_token)
    t.assigned_to_id = u_cs["id"]
    t.status = "open"
    t.updated_at = datetime.utcnow()
    t.unread_for_agent = False

    agent_name = (request.session["user"].get("first_name") or "").strip() or "Support Agent"
    try:
        push_notification(
            db,
            t.user_id,
            "📬 Your ticket has been opened",
            f"The message has been opened by {agent_name}",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except:
        pass

    db.commit()

    return RedirectResponse(f"/cs/ticket/{ticket_id}", status_code=303)


# ---------------------------
# Agent Reply
# ---------------------------
@router.post("/ticket/{tid}/reply")
async def cs_ticket_reply(
    tid: int,
    request: Request,
    body: str = Form(""),
    csrf_token: str = Form(""),
    client_message_id: str = Form(""),
    attachments: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.get(SupportTicket, tid)
    if not _is_legacy_ticket(t):
        return RedirectResponse("/cs/inbox", status_code=303)

    staff_user = db.get(User, u_cs["id"])
    if not staff_user or not staff_can_view_legacy_ticket(t, staff_user):
        return RedirectResponse("/cs/inbox", status_code=303)
    require_csrf(request, csrf_token)

    _message, created = await create_legacy_support_message(
        db,
        request=request,
        ticket=t,
        sender=staff_user,
        sender_role="agent",
        body=body,
        uploads=attachments,
        client_message_id=client_message_id,
    )

    # The reply is already committed by the shared message transaction.  A
    # notification problem must not roll back or misreport a successful send.
    if created:
        try:
            agent_name = (request.session["user"].get("first_name") or "").strip() or "Support Agent"
            push_notification(
                db,
                t.user_id,
                "💬 Reply from support",
                f"{agent_name} replied to your ticket #{t.id}",
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
            db.commit()
        except Exception:
            db.rollback()
    return RedirectResponse(f"/cs/ticket/{t.id}", status_code=303)


# ---------------------------
# Resolve Ticket
# ---------------------------
@router.post("/tickets/{ticket_id}/resolve")
def cs_resolve(
    ticket_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if not _is_legacy_ticket(t):
        return RedirectResponse("/cs/inbox", status_code=303)
    if str(t.status or "").lower() == "closed":
        return RedirectResponse(f"/cs/ticket/{ticket_id}", status_code=303)
    row = db.execute(
        text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"),
        {"tid": ticket_id},
    ).first()
    if not row or (row[0] or "cs") not in {"cs", "cs_chatbot"}:
        return RedirectResponse("/cs/inbox", status_code=303)
    staff_user = db.get(User, u_cs["id"])
    if not staff_user or not staff_can_view_legacy_ticket(t, staff_user):
        return RedirectResponse("/cs/inbox", status_code=303)
    require_csrf(request, csrf_token)
    now = datetime.utcnow()
    agent_name = (request.session["user"].get("first_name") or "").strip() or "Support Agent"

    t.status = "resolved"
    t.resolved_at = now
    t.updated_at = now
    if not t.assigned_to_id:
        t.assigned_to_id = u_cs["id"]

    close_msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_cs["id"],
        sender_role="agent",
        body=f"Ticket closed by {agent_name} at {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
    )
    db.add(close_msg)

    t.unread_for_user = True

    try:
        push_notification(
            db,
            t.user_id,
            "✅ Your ticket has been resolved",
            f"#{t.id} — {t.subject or ''}".strip(),
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except:
        pass

    db.commit()

    return RedirectResponse("/cs/inbox", status_code=303)


# ---------------------------
# Transfer Ticket
# ---------------------------
@router.post("/tickets/{ticket_id}/transfer")
def cs_transfer_queue(
    ticket_id: int,
    request: Request,
    to: str = Form(...),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    target = (to or "").strip().lower()
    allowed = {"cs", "md", "mod"}

    if target not in allowed:
        return RedirectResponse(f"/cs/ticket/{ticket_id}", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if not _is_legacy_ticket(t):
        return RedirectResponse("/cs/inbox", status_code=303)
    if str(t.status or "").lower() == "closed":
        return RedirectResponse(f"/cs/ticket/{ticket_id}", status_code=303)
    row = db.execute(
        text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"),
        {"tid": ticket_id},
    ).first()
    if not row or (row[0] or "cs") not in {"cs", "cs_chatbot"}:
        return RedirectResponse("/cs/inbox", status_code=303)
    staff_user = db.get(User, u_cs["id"])
    if not staff_user or not staff_can_view_legacy_ticket(t, staff_user):
        return RedirectResponse("/cs/inbox", status_code=303)
    require_csrf(request, csrf_token)

    # Keep the queue mutation, system message, and ticket state in one ORM
    # transaction.  Swallowing a queue write error here used to allow a false
    # "transferred" message to be committed while the ticket stayed in place.
    t.queue = target

    now = datetime.utcnow()
    agent_name = (request.session["user"].get("first_name") or "").strip() or "Support Agent"

    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_cs["id"],
        sender_role="agent",
        body=f"Ticket transferred from CS to {target.upper()} by {agent_name} at {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
    )
    db.add(msg)

    t.last_from = "agent"
    t.last_msg_at = now
    t.updated_at = now
    t.unread_for_user = True

    if target in ("md", "mod"):
        t.status = "new"
        t.assigned_to_id = None
        t.unread_for_agent = True
    else:
        t.status = "open"
        if not t.assigned_to_id:
            t.assigned_to_id = u_cs["id"]
        t.unread_for_agent = False

    try:
        push_notification(
            db,
            t.user_id,
            "↪️ Your ticket has been transferred",
            f"Your ticket has been transferred to the appropriate team ({target.upper()}).",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except:
        pass

    if target == "mod":
        try:
            notify_mods(
                db,
                title="📥 New ticket requires review (MOD)",
                body=f"{t.subject or '(No subject)'} — #{t.id}",
                url=f"/mod/inbox?tid={t.id}",
            )
        except:
            pass

    if target == "md":
        try:
            notify_dms(
                db,
                title="📥 New ticket requires processing (MD)",
                body=f"{t.subject or '(No subject)'} — #{t.id}",
                url=f"/md/inbox?tid={t.id}",
            )
        except:
            pass

    db.commit()
    return RedirectResponse(f"/cs/ticket/{t.id}", status_code=303)
