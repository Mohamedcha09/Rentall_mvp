# app/md.py
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
router = APIRouter(prefix="/md", tags=["md"])

# ---------------------------
# Helpers
# ---------------------------
def _require_login(request: Request):
    return request.session.get("user")

def _ensure_md_session(db: Session, request: Request):
    """
    مزامنة علم is_deposit_manager داخل الجلسة إذا تغيّر في قاعدة البيانات.
    """
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None
    # لو الجلسة تعرفه كـ MD بالفعل
    if bool(sess.get("is_deposit_manager")) or (str(sess.get("role", "")).lower() == "admin"):
        return sess
    # حدّث من القاعدة
    u_db = db.get(User, uid)
    if u_db and (bool(getattr(u_db, "is_deposit_manager", False)) or str(getattr(u_db, "role", "")).lower() == "admin"):
        sess["is_deposit_manager"] = bool(getattr(u_db, "is_deposit_manager", False))
        request.session["user"] = sess
        return sess
    return None

def _is_admin(sess: dict | None) -> bool:
    role = (sess or {}).get("role") or ""
    return str(role).lower() == "admin"

# ---------------------------
# Inbox (قائمة التذاكر للـ MD)
# ---------------------------
@router.get("/inbox")
def md_inbox(request: Request, db: Session = Depends(get_db), tid: int | None = None):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_md = _ensure_md_session(db, request)
    if not u_md:
        return RedirectResponse("/", status_code=303)

    # كل ما بطابور MD فقط (لا نعتمد على خاصية queue في الموديل)
    base_q = db.query(SupportTicket).filter(text("COALESCE(queue, 'cs') = 'md'"))

    # القسم 1: تم إرسالها جديد من طرف CS (غير معيّنة بعد)
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    # القسم 2: قيد المراجعة (مفتوحة ومُعيّنة لـ MD)
    in_review_q = (
        base_q.filter(
            SupportTicket.status == "open",
            SupportTicket.assigned_to_id.isnot(None),
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
    )

    # القسم 3: منتهية
    # - إن كان أدمن: يرى كل المنتهية في طابور MD
    # - غير ذلك: يرى فقط التي أغلقها بنفسه (resolved_by_id == u_md["id"])
    if _is_admin(u_md):
        resolved_q = (
            base_q.filter(SupportTicket.status == "resolved")
            .order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at))
        )
    else:
        resolved_q = (
            base_q.filter(
                SupportTicket.status == "resolved",
                text("COALESCE(resolved_by_id, 0) = :uid"),
            )
            .params(uid=int(u_md["id"]))
            .order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at))
        )

    data = {
        "new": new_q.all(),
        "in_review": in_review_q.all(),
        "resolved": resolved_q.all(),
        "focus_tid": tid or 0,  # لتسليط الضوء إن وصل من إشعار
    }

    return templates.TemplateResponse(
        "md_inbox.html",
        {"request": request, "session_user": u_md, "title": "MD Inbox", "data": data},
    )

# ---------------------------
# عرض تذكرة MD
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

    # تأكيد أنها ضمن طابور MD
    row = db.execute(text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"), {"tid": tid}).first()
    qval = (row[0] if row else "cs") or "cs"
    if qval != "md":
        return RedirectResponse("/md/inbox", status_code=303)

    # تعليم كـ مقروء للوكيل (MD)
    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "md_ticket.html",
        {"request": request, "session_user": u_md, "ticket": t, "msgs": t.messages, "title": f"تذكرة #{t.id} (MD)"},
    )

# ---------------------------
# تولّي التذكرة (Assign to me)
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
    if t:
        row = db.execute(text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"), {"tid": ticket_id}).first()
        if not row or (row[0] or "cs") != "md":
            return RedirectResponse("/md/inbox", status_code=303)

        t.assigned_to_id = u_md["id"]
        t.status = "open"
        t.updated_at = datetime.utcnow()
        t.unread_for_agent = False

        md_name = (request.session["user"].get("first_name") or "").strip() or "مسؤول الودائع"
        try:
            push_notification(
                db,
                t.user_id,
                "📬 تم فتح تذكرتك",
                f"تم فتح الرسالة من طرف {md_name}",
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
        except Exception:
            pass

        db.commit()

    return RedirectResponse(f"/md/ticket/{ticket_id}", status_code=303)

# ---------------------------
# ردّ الـ MD على التذكرة
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

    row = db.execute(text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"), {"tid": tid}).first()
    if not row or (row[0] or "cs") != "md":
        return RedirectResponse("/md/inbox", status_code=303)

    now = datetime.utcnow()
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_md["id"],
        sender_role="agent",
        body=(body or "").strip() or "(بدون نص)",
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
        md_name = (request.session["user"].get("first_name") or "").strip() or "مسؤول الودائع"
        push_notification(
            db,
            t.user_id,
            "💬 رد من فريق الودائع (MD)",
            f"ردّ عليك {md_name} في تذكرتك #{t.id}",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/md/ticket/{t.id}", status_code=303)

# ---------------------------
# إغلاق التذكرة (Resolve) — إغلاق نهائي + تأشير من أغلق
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
    if t:
        row = db.execute(text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"), {"tid": ticket_id}).first()
        if not row or (row[0] or "cs") != "md":
            return RedirectResponse("/md/inbox", status_code=303)

        now = datetime.utcnow()
        md_name = (request.session["user"].get("first_name") or "").strip() or "مسؤول الودائع"

        # حالة التذكرة
        t.status = "resolved"
        t.resolved_at = now
        t.updated_at = now
        if not t.assigned_to_id:
            t.assigned_to_id = u_md["id"]

        # قفل نهائي + من أغلق (لو الأعمدة موجودة في الجدول سيتم التحديث، إن لم توجد نتجاهل بدون كسر)
        try:
            db.execute(
                text("""
                    UPDATE support_tickets
                    SET resolved_locked = TRUE,
                        resolved_by_id = :uid,
                        updated_at = now()
                    WHERE id = :tid
                """),
                {"uid": int(u_md["id"]), "tid": int(ticket_id)},
            )
        except Exception:
            pass

        # أضف رسالة نظامية
        close_msg = SupportMessage(
            ticket_id=t.id,
            sender_id=u_md["id"],
            sender_role="agent",
            body=f"تم إغلاق التذكرة بواسطة {md_name} في {now.strftime('%Y-%m-%d %H:%M')}",
            created_at=now,
        )
        db.add(close_msg)

        # إشعار للعميل
        t.unread_for_user = True
        try:
            push_notification(
                db,
                t.user_id,
                "✅ تم حل تذكرتك (MD)",
                f"#{t.id} — {t.subject or ''}".strip(),
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
        except Exception:
            pass

        db.commit()

    return RedirectResponse("/md/inbox", status_code=303)
