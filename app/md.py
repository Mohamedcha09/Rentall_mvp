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
    """تحقق إن كان أدمن"""
    if not sess:
        return False
    return (sess.get("role") == "admin") or bool(sess.get("is_admin")) or bool(sess.get("badge_admin"))

def _ensure_md_session(db: Session, request: Request):
    """
    مزامنة علم is_deposit_manager داخل الجلسة إذا تغيّر في قاعدة البيانات.
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
# إغلاق تلقائي بعد 24h من عدم رد العميل (لطابور MD)
# ---------------------------
@router.get("/cron/auto_close_24h")
def auto_close_24h_md(request: Request, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    rows = db.execute(
        text("""
            SELECT id FROM support_tickets
            WHERE COALESCE(queue, 'cs')='md'
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
            body="تم إغلاق التذكرة تلقائيًا لعدم ردّ العميل خلال 24 ساعة.",
            created_at=now,
        ))

        t.unread_for_user = True
        try:
            push_notification(
                db,
                t.user_id,
                "⏱️ تم إغلاق التذكرة تلقائيًا",
                f"تذكرتك #{t.id} أُغلقت تلقائيًا بعد 24 ساعة دون ردّ.",
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
        except Exception:
            pass
        closed_ids.append(t.id)

    db.commit()
    return JSONResponse({"closed": closed_ids, "count": len(closed_ids)})

# ---------------------------
# Inbox (قائمة التذاكر للـ MD)
# ---------------------------
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

    is_admin = _is_admin(u_md)

    base_q = db.query(SupportTicket).filter(text("COALESCE(queue, 'cs') = 'md'"))

    # ✅ جديدة من CS (تستثني المحوَّلة)
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            text("(last_from IS NULL OR last_from <> 'system')")
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    # ✅ محوّلة من MOD (غير معيّنة وآخر حدث system)
    transferred_from_mod_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            text("last_from = 'system'")
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
    )

    # قيد المراجعة: مفتوحة ومُعيّنة
    in_review_q = (
        base_q.filter(
            SupportTicket.status == "open",
            SupportTicket.assigned_to_id.isnot(None),
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.updated_at))
    )

    # منتهية
    resolved_q = base_q.filter(SupportTicket.status == "resolved")
    if not is_admin:
        resolved_q = resolved_q.filter(SupportTicket.assigned_to_id == u_md["id"])
    resolved_q = resolved_q.order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at))

    data = {
        "new": new_q.all(),                    # تم إرسالها جديد من CS
        "from_mod": transferred_from_mod_q.all(),# ✅ القسم الجديد
        "in_review": in_review_q.all(),
        "resolved": resolved_q.all(),
        "focus_tid": tid or 0,
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

    row = db.execute(text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"), {"tid": tid}).first()
    qval = (row[0] if row else "cs") or "cs"

    # ✅ لو التذكرة ليست في طابور MD رجّع المستخدم لصندوق MD
    if qval != "md":
        return RedirectResponse(f"/md/inbox?tid={tid}", status_code=303)

    # ✅ التعيين التلقائي لو غير مُعيّنة
    now = datetime.utcnow()
    if t.assigned_to_id is None:
        t.assigned_to_id = u_md["id"]
        t.status = "open"
        t.updated_at = now

    # ✅ علّم رسائل الوكيل كمقروءة
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
    if not t:
        return RedirectResponse("/md/inbox", status_code=303)

    # ✅ غلق نهائي: ممنوع التولّي للجميع (حتى الأدمن)
    if t.status == "resolved":
        return RedirectResponse(f"/md/ticket/{ticket_id}", status_code=303)

    row = db.execute(text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"), {"tid": ticket_id}).first()
    if not row or (row[0] or "cs") != "md":
        return RedirectResponse("/md/inbox", status_code=303)

    t.assigned_to_id = u_md["id"]
    t.status = "open"
    t.updated_at = datetime.utcnow()
    t.unread_for_agent = False

    agent_name = (request.session["user"].get("first_name") or "").strip() or "مدير الوديعة"
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
    return RedirectResponse(f"/md/ticket/{ticket_id}", status_code=303)

# ---------------------------
# ردّ MD على التذكرة
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

    # ✅ غلق نهائي: ممنوع الرد للجميع (حتى الأدمن)
    if t.status == "resolved":
        return RedirectResponse(f"/md/ticket/{t.id}", status_code=303)

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
        agent_name = (request.session["user"].get("first_name") or "").strip() or "مدير الوديعة"
        push_notification(
            db,
            t.user_id,
            "💬 رد من إدارة الودائع (MD)",
            f"ردّ عليك {agent_name} في تذكرتك #{t.id}",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/md/ticket/{t.id}", status_code=303)

# ---------------------------
# إغلاق التذكرة (نهائي)
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

    row = db.execute(text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"), {"tid": ticket_id}).first()
    if not row or (row[0] or "cs") != "md":
        return RedirectResponse("/md/inbox", status_code=303)

    now = datetime.utcnow()
    agent_name = (request.session["user"].get("first_name") or "").strip() or "مدير الوديعة"

    # 🔒 إغلاق نهائي (Locked)
    t.status = "resolved"
    t.resolved_at = now
    t.updated_at = now
    if not t.assigned_to_id:
        t.assigned_to_id = u_md["id"]

    # أعلام القراءة
    t.unread_for_user = True
    t.unread_for_agent = False

    db.add(SupportMessage(
        ticket_id=t.id,
        sender_id=u_md["id"],
        sender_role="agent",
        body=f"تم إغلاق التذكرة بواسطة {agent_name} (MD) في {now.strftime('%Y-%m-%d %H:%M')}",
        created_at=now,
    ))

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


# ---------------------------
# تحويل التذكرة إلى المدقّق (MOD)
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

    # لا تحويل لو كانت مغلقة نهائياً
    if t.status == "resolved":
        return RedirectResponse(f"/md/ticket/{ticket_id}", status_code=303)

    now = datetime.utcnow()
    t.queue = "mod"
    t.assigned_to_id = None
    t.status = "open"
    t.updated_at = now
    t.last_msg_at = now
    t.last_from = "system"  # ✅ ضروري حتى يظهر في "تم تحويلها من MD"
    t.unread_for_agent = False
    t.unread_for_user = True

    db.add(SupportMessage(
        ticket_id=t.id,
        sender_id=u_md["id"],
        sender_role="system",
        body="🔁 تم تحويل التذكرة إلى فريق المراجعة (MOD) لمتابعة الحالة.",
        created_at=now,
    ))

    # إشعار للعميل
    try:
        push_notification(
            db,
            t.user_id,
            "🔁 تم تحويل تذكرتك",
            f"تذكرتك #{t.id} تم تحويلها إلى فريق المراجعة (MOD).",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    # إشعار لفريق MOD
    try:
        push_notification(
            db,
            0,
            "📩 تذكرة جديدة من MD",
            f"توجد تذكرة جديدة محولة من إدارة الودائع (MD): #{t.id}",
            url=f"/mod/ticket/{t.id}",
            kind="support",
        )
    except Exception:
        pass

    db.commit()
    return RedirectResponse("/md/inbox", status_code=303)
