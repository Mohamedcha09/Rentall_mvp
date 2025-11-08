# app/mod.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, text

from .database import get_db
from .models import SupportTicket, SupportMessage, User
from .notifications_api import push_notification

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/mod", tags=["mod"])

# ---------------------------
# Helpers
# ---------------------------
def _require_login(request: Request):
    return request.session.get("user")

def _is_admin(sess):
    """Check if the user is admin"""
    if not sess:
        return False
    return (sess.get("role") == "admin") or bool(sess.get("is_admin"))

def _ensure_mod_session(db: Session, request: Request):
    """
    Sync the is_mod flag inside the session if it changed in the database.
    """
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


# ---------------------------
# Auto-close after 24h of no customer reply
# ---------------------------
@router.get("/cron/auto_close_24h")
def auto_close_24h(request: Request, db: Session = Depends(get_db)):
    now = datetime.utcnow()

    tickets = db.execute(
        text("""
            SELECT id FROM support_tickets
            WHERE LOWER(COALESCE(queue, 'cs'))='mod'
              AND status IN ('open','new')
              AND last_from='agent'
              AND last_msg_at < (NOW() - INTERVAL '24 hours')
        """)
    ).fetchall()

    closed_ids = []
    for row in tickets:
        tid = row[0]
        t = db.get(SupportTicket, tid)
        if not t:
            continue
        t.status = "resolved"
        t.resolved_at = now
        t.updated_at = now
        msg = SupportMessage(
            ticket_id=t.id,
            sender_id=t.assigned_to_id or 0,
            sender_role="system",
            body=f"The ticket was automatically closed due to no customer reply within 24 hours.",
            created_at=now,
        )
        db.add(msg)
        t.unread_for_user = True
        try:
            push_notification(
                db,
                t.user_id,
                "⏱️ Ticket auto-closed",
                f"Your ticket #{t.id} was automatically closed after 24 hours without a reply.",
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
        except Exception:
            pass
        closed_ids.append(t.id)
    db.commit()

    return JSONResponse({"closed": closed_ids, "count": len(closed_ids)})


# ---------------------------
# Inbox (tickets list for MOD)
# ---------------------------
@router.get("/inbox")
def mod_inbox(request: Request, db: Session = Depends(get_db), tid: int | None = None):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/", status_code=303)

    is_admin = _is_admin(u_mod)

    base_q = db.query(SupportTicket).filter(text("LOWER(COALESCE(queue, 'cs')) = 'mod'"))

    # ✅ New from CS (excludes those transferred from other systems)
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            text("(last_from IS NULL OR (last_from <> 'system_md' AND last_from <> 'system_mod'))")
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    # ✅ Transferred from MD (unassigned and last event is system_md)
    transferred_from_md_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            text("last_from = 'system_md'")
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
    )

    # In review: open and assigned
    in_review_q = (
        base_q.filter(
            SupportTicket.status == "open",
            SupportTicket.assigned_to_id.isnot(None),
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
    )

    # Resolved
    resolved_q = base_q.filter(SupportTicket.status == "resolved")
    if not is_admin:
        resolved_q = resolved_q.filter(SupportTicket.assigned_to_id == u_mod["id"])
    resolved_q = resolved_q.order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at))

    data = {
        "new": new_q.all(),
        "from_md": transferred_from_md_q.all(),   # 👈 shows those transferred from MD here
        "in_review": in_review_q.all(),
        "resolved": resolved_q.all(),
        "focus_tid": tid or 0,
    }

    return templates.TemplateResponse(
        "mod_inbox.html",
        {"request": request, "session_user": u_mod, "title": "MOD Inbox", "data": data},
    )




# ---------------------------
# View a MOD ticket
# ---------------------------
@router.get("/ticket/{tid}")
def mod_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not t:
        return RedirectResponse("/mod/inbox", status_code=303)

    row = db.execute(
        text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"),
        {"tid": tid},
    ).first()
    qval = (row[0] if row else "cs") or "cs"

    if qval != "mod":
        return RedirectResponse(f"/mod/inbox?tid={tid}", status_code=303)

    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "mod_ticket.html",
        {"request": request, "session_user": u_mod, "ticket": t, "msgs": t.messages, "title": f"Ticket #{t.id} (MOD)"},
    )


# ---------------------------
# Take over the ticket (Assign to me)
# ---------------------------
@router.post("/tickets/{ticket_id}/assign_self")
def mod_assign_self(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if not t:
        return RedirectResponse("/mod/inbox", status_code=303)

    if t.status == "resolved":
        return RedirectResponse(f"/mod/ticket/{ticket_id}", status_code=303)

    row = db.execute(
        text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"),
        {"tid": ticket_id},
    ).first()
    if not row or (row[0] or "cs") != "mod":
        return RedirectResponse("/mod/inbox", status_code=303)

    t.assigned_to_id = u_mod["id"]
    t.status = "open"
    t.updated_at = datetime.utcnow()
    t.unread_for_agent = False

    mod_name = (request.session["user"].get("first_name") or "").strip() or "Content Moderator"
    try:
        push_notification(
            db,
            t.user_id,
            "📬 Your ticket was opened",
            f"Your message was opened by {mod_name}",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/mod/ticket/{ticket_id}", status_code=303)


# ---------------------------
# Moderator reply to the ticket
# ---------------------------
@router.post("/ticket/{tid}/reply")
def mod_ticket_reply(tid: int, request: Request, db: Session = Depends(get_db), body: str = Form("")):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/", status_code=303)

    t = db.get(SupportTicket, tid)
    if not t:
        return RedirectResponse("/mod/inbox", status_code=303)

    if t.status == "resolved":
        return RedirectResponse(f"/mod/ticket/{t.id}", status_code=303)

    row = db.execute(
        text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"),
        {"tid": tid},
    ).first()
    if not row or (row[0] or "cs") != "mod":
        return RedirectResponse("/mod/inbox", status_code=303)

    now = datetime.utcnow()
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="agent",
        body=(body or "").strip() or "(No text)",
        created_at=now,
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

    try:
        mod_name = (request.session["user"].get("first_name") or "").strip() or "Content Moderator"
        push_notification(
            db,
            t.user_id,
            "💬 Reply from Review Team (MOD)",
            f"{mod_name} replied to your ticket #{t.id}",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/mod/ticket/{t.id}", status_code=303)


# ---------------------------
# Resolve the ticket (final)
# ---------------------------
@router.post("/tickets/{ticket_id}/resolve")
def mod_resolve(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if not t:
        return RedirectResponse("/mod/inbox", status_code=303)

    row = db.execute(
        text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"),
        {"tid": ticket_id},
    ).first()
    if not row or (row[0] or "cs") != "mod":
        return RedirectResponse("/mod/inbox", status_code=303)

    now = datetime.utcnow()
    mod_name = (request.session["user"].get("first_name") or "").strip() or "Content Moderator"

    t.status = "resolved"
    t.resolved_at = now
    t.updated_at = now
    if not t.assigned_to_id:
        t.assigned_to_id = u_mod["id"]

    close_msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="agent",
        body=f"The ticket was closed by {mod_name} (MOD) on {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
    )
    db.add(close_msg)

    t.unread_for_user = True
    try:
        push_notification(
            db,
            t.user_id,
            "✅ Your ticket has been resolved (MOD)",
            f"#{t.id} — {t.subject or ''}".strip(),
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse("/mod/inbox", status_code=303)


# ---------------------------
# Transfer the ticket to Deposit Manager (MD)
# ---------------------------
@router.post("/tickets/{ticket_id}/transfer_to_md")
def mod_transfer_to_md(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if not t:
        return RedirectResponse("/mod/inbox", status_code=303)
    if t.status == "resolved":
        return RedirectResponse(f"/mod/ticket/{ticket_id}", status_code=303)

    now = datetime.utcnow()
    # 1) Move the ticket to md and record a system_mod message (direction: MOD → MD)
    t.queue = "md"
    t.assigned_to_id = None
    t.status = "open"
    t.updated_at = now
    t.last_msg_at = now
    t.last_from = "system_mod"  # ⬅️ Important: so it appears under "Transferred from MOD" for MD
    t.unread_for_agent = False
    t.unread_for_user = True

    db.add(SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="system",
        body="[XFER_MOD_TO_MD] 🔁 The ticket has been transferred to Deposit Management (MD) for further handling.",
        created_at=now,
    ))

    # 2) Persist the transfer first
    db.commit()

    # 3) Notify the customer
    try:
        push_notification(
            db,
            t.user_id,
            "🔁 Your ticket was transferred",
            f"Your ticket #{t.id} has been transferred to Deposit Management (MD).",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
        db.commit()
    except Exception:
        db.rollback()

    # 4) Notify all MD members
    try:
        md_users = db.query(User.id).filter(User.is_deposit_manager.is_(True)).all()
        for (md_id,) in md_users:
            push_notification(
                db,
                md_id,
                "📩 New ticket from MOD",
                f"There is a ticket transferred from the Review Team (MOD): #{t.id}",
                url=f"/md/ticket/{t.id}",
                kind="support",
            )
        db.commit()
    except Exception:
        db.rollback()

    return RedirectResponse("/mod/inbox", status_code=303)
