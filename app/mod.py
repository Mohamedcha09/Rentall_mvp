# app/mod.py
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
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

def _ensure_mod_session(db: Session, request: Request):
    """
    مزامنة علم is_mod داخل الجلسة إذا تغيّر في قاعدة البيانات.
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
# Inbox (قائمة التذاكر للـ MOD)
# ---------------------------
@router.get("/inbox")
def mod_inbox(request: Request, db: Session = Depends(get_db), tid: int | None = None):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_mod = _ensure_mod_session(db, request)
    if not u_mod:
        return RedirectResponse("/", status_code=303)

    # فلترة كل ما هو ضمن طابور MOD (بدون الاعتماد على خاصية queue في الموديل)
    base_q = db.query(SupportTicket).filter(text("COALESCE(queue, 'cs') = 'mod'"))

    # تم إرسالها جديد من طرف CS: غير معيّنة بعد
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    # قيد المراجعة: مفتوحة ومُعيّنة لمدقّق
    in_review_q = (
        base_q.filter(
            SupportTicket.status == "open",
            SupportTicket.assigned_to_id.isnot(None),
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
    )

    # منتهية
    resolved_q = (
        base_q.filter(SupportTicket.status == "resolved")
        .order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at))
    )

    data = {
        "new": new_q.all(),
        "in_review": in_review_q.all(),
        "resolved": resolved_q.all(),
        "focus_tid": tid or 0,
    }

    return templates.TemplateResponse(
        "mod_inbox.html",
        {"request": request, "session_user": u_mod, "title": "MOD Inbox", "data": data},
    )

# ---------------------------
# عرض تذكرة MOD
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
        text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"),
        {"tid": tid},
    ).first()
    qval = (row[0] if row else "cs") or "cs"
    if qval != "mod":
        return RedirectResponse("/mod/inbox", status_code=303)

    # تعليم كـ مقروء للمدقق
    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "mod_ticket.html",
        {
            "request": request,
            "session_user": u_mod,
            "ticket": t,
            "msgs": t.messages,
            "title": f"تذكرة #{t.id} (MOD)",
        },
    )

# ---------------------------
# تولّي التذكرة (Assign to me)
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
    if t:
        row = db.execute(
            text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"),
            {"tid": ticket_id},
        ).first()
        if not row or (row[0] or "cs") != "mod":
            return RedirectResponse("/mod/inbox", status_code=303)

        t.assigned_to_id = u_mod["id"]
        t.status = "open"
        t.updated_at = datetime.utcnow()
        t.unread_for_agent = False

        mod_name = (request.session["user"].get("first_name") or "").strip() or "مدقّق المحتوى"
        try:
            push_notification(
                db,
                t.user_id,
                "📬 تم فتح تذكرتك",
                f"تم فتح الرسالة من طرف {mod_name}",
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
        except Exception:
            pass

        db.commit()

    return RedirectResponse(f"/mod/ticket/{ticket_id}", status_code=303)

# ---------------------------
# ردّ المدقق على التذكرة
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

    row = db.execute(
        text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"),
        {"tid": tid},
    ).first()
    if not row or (row[0] or "cs") != "mod":
        return RedirectResponse("/mod/inbox", status_code=303)

    now = datetime.utcnow()
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="agent",
        body=(body or "").strip() or "(بدون نص)",
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
        mod_name = (request.session["user"].get("first_name") or "").strip() or "مدقّق المحتوى"
        push_notification(
            db,
            t.user_id,
            "💬 رد من فريق المراجعة (MOD)",
            f"ردّ عليك {mod_name} في تذكرتك #{t.id}",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/mod/ticket/{t.id}", status_code=303)

# ---------------------------
# إغلاق التذكرة (Resolve)
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
    if t:
        row = db.execute(
            text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"),
            {"tid": ticket_id},
        ).first()
        if not row or (row[0] or "cs") != "mod":
            return RedirectResponse("/mod/inbox", status_code=303)

        now = datetime.utcnow()
        mod_name = (request.session["user"].get("first_name") or "").strip() or "مدقّق المحتوى"

        t.status = "resolved"
        t.resolved_at = now
        t.updated_at = now
        if not t.assigned_to_id:
            t.assigned_to_id = u_mod["id"]

        close_msg = SupportMessage(
            ticket_id=t.id,
            sender_id=u_mod["id"],
            sender_role="agent",
            body=f"تم إغلاق التذكرة بواسطة {mod_name} في {now.strftime('%Y-%m-%d %H:%M')}",
            created_at=now,
        )
        db.add(close_msg)

        t.unread_for_user = True
        try:
            push_notification(
                db,
                t.user_id,
                "✅ تم حل تذكرتك (MOD)",
                f"#{t.id} — {t.subject or ''}".strip(),
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
        except Exception:
            pass

        db.commit()

    return RedirectResponse("/mod/inbox", status_code=303)
