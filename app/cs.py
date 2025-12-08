# app/cs.py
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, text

from .database import get_db
from .models import SupportTicket, SupportMessage, User
from .notifications_api import push_notification, notify_mods, notify_dms


templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/cs", tags=["cs"])

# ---------------------------
# Helpers
# ---------------------------
def _require_login(request: Request):
    return request.session.get("user")

def _ensure_cs_session(db: Session, request: Request):
    """
    Synchronize is_support flag inside the session if it changes in the database.
    """
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

# ---------------------------
# Inbox (Ticket list for CS)
# ---------------------------
@router.get("/inbox")
def cs_inbox(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    # Important: CS inbox should not show tickets transferred to MOD/MD
    base_q = db.query(SupportTicket).filter(text("COALESCE(queue,'cs') = 'cs'"))

    # New: unassigned + last message from client + unread for agent
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            SupportTicket.unread_for_agent.is_(True),
            SupportTicket.last_from == "user",
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    # In review: open and assigned to agent
    in_review_q = (
        base_q.filter(
            SupportTicket.status == "open",
            SupportTicket.assigned_to_id.isnot(None),
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
    )

    # Resolved
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
        "cs_inbox.html",
        {"request": request, "session_user": u_cs, "title": "CS Inbox", "data": data},
    )

# ---------------------------
# View CS Ticket
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
    if not t:
        return RedirectResponse("/cs/inbox", status_code=303)

    # Mark as read for the agent
    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "cs_ticket.html",
        {"request": request, "session_user": u_cs, "ticket": t, "msgs": t.messages, "title": f"Ticket #{t.id} (CS)"},
    )

# ---------------------------
# Take ownership of the ticket (Assign to me)
# ---------------------------
@router.post("/tickets/{ticket_id}/assign_self")
def cs_assign_self(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if t:
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
        except Exception:
            pass

        db.commit()

    return RedirectResponse(f"/cs/ticket/{ticket_id}", status_code=303)

# ---------------------------
# Agent reply to ticket
# ---------------------------
@router.post("/ticket/{tid}/reply")
def cs_ticket_reply(tid: int, request: Request, db: Session = Depends(get_db), body: str = Form("")):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.get(SupportTicket, tid)
    if not t:
        return RedirectResponse("/cs/inbox", status_code=303)

    now = datetime.utcnow()
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_cs["id"],
        sender_role="agent",
        body=(body or "").strip() or "(no text)",
        created_at=now,
    )
    db.add(msg)

    t.last_msg_at = now
    t.updated_at = now
    t.last_from = "agent"
    if not t.assigned_to_id:
        t.assigned_to_id = u_cs["id"]
    t.status = "open"
    t.unread_for_user = True
    t.unread_for_agent = False

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
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/cs/ticket/{t.id}", status_code=303)

# ---------------------------
# Close the ticket (Resolve)
# ---------------------------
@router.post("/tickets/{ticket_id}/resolve")
def cs_resolve(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if t:
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
        except Exception:
            pass

        db.commit()

    return RedirectResponse("/cs/inbox", status_code=303)

# ---------------------------
# Transfer ticket between departments (CS → MD → MOD)
# ---------------------------
@router.post("/tickets/{ticket_id}/transfer")
def cs_transfer_queue(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    to: str = Form(...),  # values: cs / md / mod
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
    if not t:
        return RedirectResponse("/cs/inbox", status_code=303)

    # Update queue directly (the column might not be defined in the model)
    try:
        db.execute(
            text("UPDATE support_tickets SET queue = :q, updated_at = now() WHERE id = :tid"),
            {"q": target, "tid": ticket_id},
        )
    except Exception:
        pass

    now = datetime.utcnow()
    agent_name = (request.session["user"].get("first_name") or "").strip() or "Support Agent"

    # System message to explain transfer
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_cs["id"],
        sender_role="agent",
        body=f"Ticket transferred from CS to {target.upper()} by {agent_name} at {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
    )
    db.add(msg)

    # Keep status open/new + unread flags
    t.last_from = "agent"
    t.last_msg_at = now
    t.updated_at = now
    t.unread_for_user = True

    # ✅ Important: when transferring to MD or MOD → mark as 'new' and unassigned so it appears in 'New from CS' inbox
    if target in ("md", "mod"):
        t.status = "new"
        t.assigned_to_id = None
        t.unread_for_agent = True
    else:
        # Back to CS
        t.status = "open"
        if not t.assigned_to_id:
            t.assigned_to_id = u_cs["id"]
        t.unread_for_agent = False

    # Notify client
    try:
        push_notification(
            db,
            t.user_id,
            "↪️ Your ticket has been transferred",
            f"Your ticket has been transferred to the appropriate team ({target.upper()}).",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    # Notify moderators only if transfer to MOD
    if target == "mod":
        try:
            notify_mods(
                db,
                title="📥 New ticket requires review (MOD)",
                body=f"{t.subject or '(No subject)'} — #{t.id}",
                url=f"/mod/inbox?tid={t.id}",
            )
        except Exception:
            pass

    # ✅ Notify deposit managers if transfer to MD
    if target == "md":
        try:
            notify_mds(
                db,
                title="📥 New ticket requires processing (MD)",
                body=f"{t.subject or '(No subject)'} — #{t.id}",
                url=f"/md/inbox?tid={t.id}",
            )
        except Exception:
            pass

    db.commit()
    return RedirectResponse(f"/cs/ticket/{t.id}", status_code=303)
