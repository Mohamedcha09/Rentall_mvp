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
    """تحقق إن كان المستخدم أدمن"""
    if not sess:
        return False
    return (sess.get("role") == "admin") or bool(sess.get("is_admin"))

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
# إغلاق تلقائي بعد 24h من عدم الرد من العميل
# ---------------------------
@router.get("/cron/auto_close_24h")
def auto_close_24h(request: Request, db: Session = Depends(get_db)):
    now = datetime.utcnow()

    tickets = db.execute(
        text("""
            SELECT id FROM support_tickets
            WHERE COALESCE(queue, 'cs')='mod'
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
            body=f"تم إغلاق التذكرة تلقائيًا لعدم ردّ العميل خلال 24 ساعة.",
            created_at=now,
        )
        db.add(msg)
        t.unread_for_user = True
        try:
            push_notification(
                db,
                t.user_id,
                "⏱️ تم إغلاق التذكرة تلقائيًا",
                f"تذكرتك #{t.id} أغلقت تلقائيًا بعد 24 ساعة دون ردّ.",
                url=f"/support/ticket/{t.id}",
                kind="support",
            )
        except Exception:
            pass
        closed_ids.append(t.id)
    db.commit()

    return JSONResponse({"closed": closed_ids, "count": len(closed_ids)})


# ---------------------------
# Inbox (قائمة التذاكر للـ MOD)
# ---------------------------
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

    is_admin = _is_admin(u_mod)

    base_q = db.query(SupportTicket).filter(text("COALESCE(queue, 'cs') = 'mod'"))

    # ✅ جديدة من CS (تستثني المحوَّلة)
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            # last_from != 'system' OR NULL
            text("(last_from IS NULL OR last_from <> 'system')")
        )
        .order_by(desc(SupportTicket.last_msg_at), desc(SupportTicket.created_at))
    )

    # ✅ محوّلة من MD (غير معيّنة وآخر حدث system)
    transferred_from_md_q = (
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
        resolved_q = resolved_q.filter(SupportTicket.assigned_to_id == u_mod["id"])
    resolved_q = resolved_q.order_by(desc(SupportTicket.resolved_at), desc(SupportTicket.updated_at))

    data = {
        "new": new_q.all(),                    # تم إرسالها جديد من CS
        "from_md": transferred_from_md_q.all(),# ✅ القسم الجديد
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

    # ✅ لو التذكرة ليست في طابور MOD رجّع المستخدم لصندوق MOD (مش MD)
    if qval != "mod":
        return RedirectResponse(f"/mod/inbox?tid={tid}", status_code=303)

    # ✅ علّم رسائل الوكيل كمقروءة
    t.unread_for_agent = False
    db.commit()

    return templates.TemplateResponse(
        "mod_ticket.html",
        {"request": request, "session_user": u_mod, "ticket": t, "msgs": t.messages, "title": f"تذكرة #{t.id} (MOD)"},
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
    if not t:
        return RedirectResponse("/mod/inbox", status_code=303)

    # ✅ غلق نهائي: ممنوع التولّي للجميع (حتى الأدمن)
    if t.status == "resolved":
        return RedirectResponse(f"/mod/ticket/{ticket_id}", status_code=303)

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

    # ✅ غلق نهائي: ممنوع الرد للجميع (حتى الأدمن)
    if t.status == "resolved":
        return RedirectResponse(f"/mod/ticket/{t.id}", status_code=303)

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
# إغلاق التذكرة (نهائي)
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
        text("SELECT COALESCE(queue,'cs') FROM support_tickets WHERE id=:tid"),
        {"tid": ticket_id},
    ).first()
    if not row or (row[0] or "cs") != "mod":
        return RedirectResponse("/mod/inbox", status_code=303)

    now = datetime.utcnow()
    mod_name = (request.session["user"].get("first_name") or "").strip() or "مدقّق المحتوى"

    # ✅ غلق نهائي: حالة مقفلة
    t.status = "resolved"
    t.resolved_at = now
    t.updated_at = now
    if not t.assigned_to_id:
        t.assigned_to_id = u_mod["id"]

    close_msg = SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="agent",
        body=f"تم إغلاق التذكرة بواسطة {mod_name} (MOD) في {now.strftime('%Y-%m-%d %H:%M')}",
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


# ---------------------------
# تحويل التذكرة إلى مدير الوديعة (MD)
# ---------------------------
# ---------------------------
# تحويل التذكرة إلى مدير الوديعة (MD)
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
    # 1) انقل التذكرة إلى md وسجّل رسالة system
    t.queue = "md"
    t.assigned_to_id = None
    t.status = "open"
    t.updated_at = now
    t.last_msg_at = now
    t.last_from = "system"
    t.unread_for_agent = False
    t.unread_for_user = True

    db.add(SupportMessage(
        ticket_id=t.id,
        sender_id=u_mod["id"],
        sender_role="system",
        body="🔁 تم تحويل التذكرة إلى إدارة الودائع (MD) لمتابعة الحالة.",
        created_at=now,
    ))

    # 2) ثبّت التحويل أولًا
    db.commit()

    # 3) إشعار العميل
    try:
        push_notification(
            db,
            t.user_id,
            "🔁 تم تحويل تذكرتك",
            f"تذكرتك #{t.id} تم تحويلها إلى إدارة الودائع (MD).",
            url=f"/support/ticket/{t.id}",
            kind="support",
        )
        db.commit()
    except Exception:
        db.rollback()

    # 4) إشعار كل أعضاء MD (is_deposit_manager = True)
    try:
        md_users = db.query(User.id).filter(getattr(User, "is_deposit_manager", False) == True).all()
        if md_users:
            for (md_id,) in md_users:
                push_notification(
                    db,
                    md_id,
                    "📩 تذكرة جديدة من MOD",
                    f"توجد تذكرة محوّلة من فريق المراجعة (MOD): #{t.id}",
                    url=f"/md/ticket/{t.id}",
                    kind="support",
                )
            db.commit()
    except Exception:
        db.rollback()

    return RedirectResponse("/mod/inbox", status_code=303)
