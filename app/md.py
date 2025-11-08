# app/md.py
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
router = APIRouter(prefix="/md", tags=["md"])

# ---------------------------
# Helpers
# ---------------------------
def _require_login(request: Request):
    return request.session.get("user")

def _is_admin(sess):
    """Check if user is admin"""
    if not sess:
        return False
    return (sess.get("role") == "admin") or bool(sess.get("is_admin")) or bool(sess.get("badge_admin"))

def _ensure_md_session(db: Session, request: Request):
    """
    Sync the is_deposit_manager flag inside the session if it changed in the database.
    """
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None
    if bool(sess.get("is_deposit_manager")):
        return sess
    u_db = db.get(User, uid)
    if u_db and bool(getattr(u_db, "is_deposit_manager", False)):
        sess["is_deposit_manager"] = True
        request.session["user"] = sess
        return sess
    return None


# ---------------------------
# Auto close after 24h of no customer reply (for MD queue)
# ---------------------------
@router.get("/cron/auto_close_24h")
def auto_close_24h_md(request: Request, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    rows = db.execute(
        text("""
            SELECT id FROM support_tickets
            WHERE LOWER(COALESCE(queue, 'cs'))='md'
              AND status IN ('open','new')
              AND last_from='agent'
              AND last_msg_at < (NOW() - INTERVAL '24 hours')
        """)
    ).fetchall()

    closed_ids = []
    for r in rows:
        t = db.get(SupportTicket, r[0])
        if not t:
            continue
        t.status = "resolved"
        t.resolved_at = now
        t.updated_at = now

        db.add(SupportMessage(
            ticket_id=t.id,
            sender_id=t.assigned_to_id or 0,
            sender_role="system",
            body="Ticket was closed automatically due to no customer reply within 24 hours.",
            created_at=now,
        ))

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
# Inbox (tickets list for MD)
# ---------------------------
@router.get("/inbox")
def md_inbox(request: Request, db: Session = Depends(get_db), tid: int | None = None):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/", status_code=303)

    is_admin = _is_admin(u_md)

    base_q = db.query(SupportTicket).filter(text("LOWER(COALESCE(queue, 'cs')) = 'md'"))

    # ✅ New from CS (excludes those transferred from other systems)
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            text("(last_from IS NULL OR (last_from <> 'system_md' AND last_from <> 'system_mod'))")
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    # ✅ Transferred from MOD (unassigned and last event is system_mod)
    transferred_from_mod_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            text("last_from = 'system_mod'")
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
        resolved_q = resolved_q.filter(SupportTicket.assigned_to_id == u_md["id"])
    resolved_q = resolved_q.order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at))

    data = {
        "new": new_q.all(),
        "from_mod": transferred_from_mod_q.all(),  # 👈 Appears here when transferred from MOD
        "in_review": in_review_q.all(),
        "resolved": resolved_q.all(),
        "focus_tid": tid or 0,
    }

    return templates.TemplateResponse(
        "md_inbox.html",
        {"request": request, "session_user": u_md, "title": "MD Inbox", "data": data},
    )



# ---------------------------
# View MD ticket
# ---------------------------
@router.get("/ticket/{tid}")
def md_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not t:
        return RedirectResponse("/md/inbox", status_code=303)

    row = db.execute(text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"), {"tid": tid}).first()
    qval = (row[0] if row else "cs") or "cs"

    if qval != "md":
        return RedirectResponse(f"/md/inbox?tid={tid}", status_code=303)

    now = datetime.utcnow()
    if t.assigned_to_id is None:
        t.assigned_to_id = u_md["id"]
        t.status = "open"
        t.updated_at = now

    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "md_ticket.html",
        {"request": request, "session_user": u_md, "ticket": t, "msgs": t.messages, "title": f"Ticket #{t.id} (MD)"},
    )


# ---------------------------
# Take over the ticket (Assign to me)
# ---------------------------
@router.post("/tickets/{ticket_id}/assign_self")
def md_assign_self(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if not t:
        return RedirectResponse("/md/inbox", status_code=303)

    if t.status == "resolved":
        return RedirectResponse(f"/md/ticket/{ticket_id}", status_code=303)

    row = db.execute(text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"), {"tid": ticket_id}).first()
    if not row or (row[0] or "cs") != "md":
        return RedirectResponse("/md/inbox", status_code=303)

    t.assigned_to_id = u_md["id"]
    t.status = "open"
    t.updated_at = datetime.utcnow()
    t.unread_for_agent = False

    agent_name = (request.session["user"].get("first_name") or "").strip() or "Deposit Manager"
    try:
        push_notification(
            db,
            t.user_id,
            "📬 Your ticket was opened",
            f"The message was opened by {agent_name}",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/md/ticket/{ticket_id}", status_code=303)


# ---------------------------
# MD reply to ticket
# ---------------------------
@router.post("/ticket/{tid}/reply")
def md_ticket_reply(tid: int, request: Request, db: Session = Depends(get_db), body: str = Form("")):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/", status_code=303)

    t = db.get(SupportTicket, tid)
    if not t:
        return RedirectResponse("/md/inbox", status_code=303)

    if t.status == "resolved":
        return RedirectResponse(f"/md/ticket/{t.id}", status_code=303)

    row = db.execute(text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"), {"tid": tid}).first()
    if not row or (row[0] or "cs") != "md":
        return RedirectResponse("/md/inbox", status_code=303)

    now = datetime.utcnow()
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_md["id"],
        sender_role="agent",
        body=(body or "").strip() or "(No text)",
        created_at=now,
    )
    db.add(msg)

    t.last_msg_at = now
    t.updated_at = now
    t.last_from = "agent"
    if not t.assigned_to_id:
        t.assigned_to_id = u_md["id"]
    t.status = "open"
    t.unread_for_user = True
    t.unread_for_agent = False

    try:
        agent_name = (request.session["user"].get("first_name") or "").strip() or "Deposit Manager"
        push_notification(
            db,
            t.user_id,
            "💬 Reply from Deposit Management (MD)",
            f"{agent_name} replied to your ticket #{t.id}",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/md/ticket/{t.id}", status_code=303)


# ---------------------------
# Resolve the ticket (final)
# ---------------------------
@router.post("/tickets/{ticket_id}/resolve")
def md_resolve(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if not t:
        return RedirectResponse("/md/inbox", status_code=303)

    row = db.execute(text("SELECT LOWER(COALESCE(queue,'cs')) FROM support_tickets WHERE id=:tid"), {"tid": ticket_id}).first()
    if not row or (row[0] or "cs") != "md":
        return RedirectResponse("/md/inbox", status_code=303)

    now = datetime.utcnow()
    agent_name = (request.session["user"].get("first_name") or "").strip() or "Deposit Manager"

    t.status = "resolved"
    t.resolved_at = now
    t.updated_at = now
    if not t.assigned_to_id:
        t.assigned_to_id = u_md["id"]

    t.unread_for_user = True
    t.unread_for_agent = False

    db.add(SupportMessage(
        ticket_id=t.id,
        sender_id=u_md["id"],
        sender_role="agent",
        body=f"Ticket was closed by {agent_name} (MD) on {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
    ))

    try:
        push_notification(
            db,
            t.user_id,
            "✅ Your ticket was resolved (MD)",
            f"#{t.id} — {t.subject or ''}".strip(),
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse("/md/inbox", status_code=303)


# ---------------------------
# Transfer the ticket to Moderator (MOD)
# ---------------------------
@router.post("/tickets/{ticket_id}/transfer_to_mod")
def md_transfer_to_mod(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if not t:
        return RedirectResponse("/md/inbox", status_code=303)
    if t.status == "resolved":
        return RedirectResponse(f"/md/ticket/{ticket_id}", status_code=303)

    now = datetime.utcnow()
    # 1) Move ticket to mod and record system_md message (direction: MD → MOD)
    t.queue = "mod"
    t.assigned_to_id = None
    t.status = "open"
    t.updated_at = now
    t.last_msg_at = now
    t.last_from = "system_md"  # ⬅️ Important: to appear under "Transferred from MD" in MOD
    t.unread_for_agent = False
    t.unread_for_user = True

    db.add(SupportMessage(
        ticket_id=t.id,
        sender_id=u_md["id"],
        sender_role="system",
        body="[XFER_MD_TO_MOD] 🔁 Ticket transferred to the Review team (MOD) for further handling.",
        created_at=now,
    ))

    # 2) Commit transfer first
    db.commit()

    # 3) Notify customer
    try:
        push_notification(
            db,
            t.user_id,
            "🔁 Your ticket was transferred",
            f"Your ticket #{t.id} has been transferred to the review team (MOD).",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
        db.commit()
    except Exception:
        db.rollback()  # fail notification only

    # 4) Notify all MOD members
    try:
        mod_users = db.query(User.id).filter(User.is_mod.is_(True)).all()
        for (mod_id,) in mod_users:
            push_notification(
                db,
                mod_id,
                "📩 New ticket from MD",
                f"A ticket was transferred from Deposit Management (MD): #{t.id}",
                url=f"/mod/ticket/{t.id}",
                kind="support",
            )
        db.commit()
    except Exception:
        db.rollback()

    return RedirectResponse("/md/inbox", status_code=303)
