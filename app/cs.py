# app/cs.py
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, text

from .database import get_db
from .models import SupportTicket, SupportMessage, User
from .notifications_api import push_notification, notify_mods

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/cs", tags=["cs"])

# ---------------------------
# Helpers
# ---------------------------
def _require_login(request: Request):
    return request.session.get("user")

def _ensure_cs_session(db: Session, request: Request):
    """
    مزامنة علم is_support داخل الجلسة إذا تغيّر في قاعدة البيانات.
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
# Inbox (قائمة التذاكر للـ CS)
# ---------------------------
@router.get("/inbox")
def cs_inbox(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    # مهم: صناديق CS يجب أن لا تُظهر ما تم تحويله إلى MOD/MD
    base_q = db.query(SupportTicket).filter(text("COALESCE(queue,'cs') = 'cs'"))

    # جديدة: غير مُعيّنة + آخر رسالة من العميل + غير مقروءة للوكيل
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            SupportTicket.unread_for_agent.is_(True),
            SupportTicket.last_from == "user",
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    # قيد المراجعة: مفتوحة ومُعيّنة لوكيل
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
    }

    return templates.TemplateResponse(
        "cs_inbox.html",
        {"request": request, "session_user": u_cs, "title": "CS Inbox", "data": data},
    )

# ---------------------------
# عرض تذكرة CS
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

    # تعليم كـ مقروء للوكيل
    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "cs_ticket.html",
        {"request": request, "session_user": u_cs, "ticket": t, "msgs": t.messages, "title": f"تذكرة #{t.id} (CS)"},
    )

# ---------------------------
# تولّي التذكرة (Assign to me)
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

        agent_name = (request.session["user"].get("first_name") or "").strip() or "موظّف الدعم"
        try:
            push_notification(
                db,
                t.user_id,
                "📬 تم فتح تذكرتك",
                f"تم فتح الرسالة من طرف {agent_name}",
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
        except Exception:
            pass

        db.commit()

    return RedirectResponse(f"/cs/ticket/{ticket_id}", status_code=303)

# ---------------------------
# ردّ الوكيل على التذكرة
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
        body=(body or "").strip() or "(بدون نص)",
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
        agent_name = (request.session["user"].get("first_name") or "").strip() or "موظّف الدعم"
        push_notification(
            db,
            t.user_id,
            "💬 رد من الدعم",
            f"ردّ عليك {agent_name} في تذكرتك #{t.id}",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/cs/ticket/{t.id}", status_code=303)

# ---------------------------
# إغلاق التذكرة (Resolve)
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
        agent_name = (request.session["user"].get("first_name") or "").strip() or "موظّف الدعم"

        t.status = "resolved"
        t.resolved_at = now
        t.updated_at = now
        if not t.assigned_to_id:
            t.assigned_to_id = u_cs["id"]

        close_msg = SupportMessage(
            ticket_id=t.id,
            sender_id=u_cs["id"],
            sender_role="agent",
            body=f"تم إغلاق التذكرة بواسطة {agent_name} في {now.strftime('%Y-%m-%d %H:%M')}",
            created_at=now,
        )
        db.add(close_msg)

        t.unread_for_user = True
        try:
            push_notification(
                db,
                t.user_id,
                "✅ تم حل تذكرتك",
                f"#{t.id} — {t.subject or ''}".strip(),
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
        except Exception:
            pass

        db.commit()

    return RedirectResponse("/cs/inbox", status_code=303)

# ---------------------------
# تحويل التذكرة بين الأقسام (CS → MD → MOD)
# ---------------------------
@router.post("/tickets/{ticket_id}/transfer")
def cs_transfer_queue(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    to: str = Form(...),  # القيم: cs / md / mod
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

    # تحدّيث queue مباشرة (قد لا يكون العمود مُعرّفًا في الموديل)
    try:
        db.execute(
            text("UPDATE support_tickets SET queue = :q, updated_at = now() WHERE id = :tid"),
            {"q": target, "tid": ticket_id},
        )
    except Exception:
        pass

    now = datetime.utcnow()
    agent_name = (request.session["user"].get("first_name") or "").strip() or "موظّف الدعم"

    # رسالة نظامية توضح التحويل
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_cs["id"],
        sender_role="agent",
        body=f"تم تحويل التذكرة من CS إلى {target.upper()} بواسطة {agent_name} في {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
    )
    db.add(msg)

    # إبقاء الحالة مفتوحة + أعلام القراءة
    t.status = "open"
    t.last_from = "agent"
    t.last_msg_at = now
    t.updated_at = now
    t.unread_for_user = True

    # مهم: عند التحويل إلى MOD نتركها غير مُعيّنة، ونعلّمها جديدة للـ agent هناك
    if target == "mod":
        t.assigned_to_id = None
        t.unread_for_agent = True
    else:
        # في غير ذلك: تبقى للـ CS الحالي
        if not t.assigned_to_id:
            t.assigned_to_id = u_cs["id"]
        t.unread_for_agent = False

    # إشعار للعميل
    try:
        push_notification(
            db,
            t.user_id,
            "↪️ تم تحويل تذكرتك",
            f"تم تحويل تذكرتك إلى الفريق المختص ({target.upper()}).",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    # إشعار المُدقّقين فقط إذا التحويل إلى MOD
    if target == "mod":
        try:
            notify_mods(
                db,
                title="📥 تذكرة جديدة تحتاج مراجعة (MOD)",
                body=f"{t.subject or '(بدون عنوان)'} — #{t.id}",
                url=f"/mod/inbox?tid={t.id}",
            )
        except Exception:
            pass

    db.commit()
    return RedirectResponse(f"/cs/ticket/{t.id}", status_code=303)
