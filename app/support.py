# app/support.py
from datetime import datetime

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import SupportTicket, SupportMessage, User

# ✅ استيراد دالة الإشعارات الداخلية
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
        # آخر رسالة من الدعم
        t.last_from = "agent"
        # تأكيد التعيين + إبقاءها مفتوحة
        if not t.assigned_to_id:
            t.assigned_to_id = author_user.id
        if t.status in (None, "new", "resolved"):
            t.status = "open"
        # قرئت من الوكيل الآن
        t.unread_for_agent = False
        # لو العميل سيرى الرد: علم لغير مقروء للمستخدم
        t.unread_for_user = True
    else:
        # آخر رسالة من العميل
        t.last_from = "user"
        # لو كانت مغلقة نعيد فتحها
        if t.status == "resolved":
            t.status = "open"
        # أصبحت غير مقروءة للوكيل
        t.unread_for_agent = True

    db.commit()


def _ensure_cs_session(db: Session, request: Request):
    """
    ✅ تُستخدم كـ "fallback" ذكي:
    - إن كانت الجلسة لا تحمل is_support=True لكن المستخدم في DB صار CS،
      نحدّث الجلسة فورًا داخل نفس الطلب ونُعيد session_user المحدَّث.
    - إن لم يكن مسجلاً أو لم يكن CS فعلاً، نُعيد None.
    """
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None

    # لو الجلسة فيها is_support=True بالفعل، ارجعها كما هي
    if bool(sess.get("is_support", False)):
        return sess

    # جلسة قديمة؟ تحقق من DB
    u_db = db.get(User, uid)
    if u_db and bool(getattr(u_db, "is_support", False)):
        # حدّث الجلسة في نفس الطلب ثم أعدها
        sess["is_support"] = True
        request.session["user"] = sess
        return sess

    # ليس CS فعلاً
    return None


# ✅ دالة ترسل إشعارًا لكل موظف CS عند فتح تذكرة جديدة
def _notify_support_agents_on_new_ticket(db: Session, ticket: SupportTicket):
    agents = (
        db.query(User)
        .filter(User.is_support == True, User.status == "approved")
        .all()
    )
    # يمكنك الإبقاء على الرابط المباشر للتذكرة أو جعله /cs/inbox حسب تفضيل الفريق
    url = f"/cs/ticket/{ticket.id}"
    title = "🎫 تذكرة دعم جديدة"
    body = f"#{ticket.id} — {ticket.subject or ''}".strip()

    for ag in agents:
        try:
            push_notification(
                db,
                ag.id,
                title,
                body,
                url,
                "support",  # نوع الإشعار
            )
        except Exception:
            # لا نوقف إنشاء التذكرة إذا فشل إشعار واحد
            pass


# ========== واجهة العميل ==========

@router.get("/support/new", response_class=HTMLResponse)
def support_new(request: Request):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "support_new.html",
        {"request": request, "session_user": u, "title": "مراسلة الدعم"},
    )


@router.post("/support/new")
def support_new_post(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    # Starlette يحفظ آخر فورم في request._form — نوفر بديل آمن لو غير متاح
    form = getattr(request, "_form", None)
    if form is None:
        import anyio

        async def _read_form():
            return await request.form()

        form = anyio.from_thread.run(_read_form)

    subject = form.get("subject", "").strip() if form else ""
    body = form.get("body", "").strip() if form else ""

    if not subject:
        subject = "بدون عنوان"

    # إنشاء التذكرة + أول رسالة
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
        body=body or "(بدون نص)",
        created_at=datetime.utcnow(),
    )
    db.add(m)
    db.commit()

    # ✅ بعد إنشاء التذكرة بنجاح: أرسل إشعارات للـ CS
    _notify_support_agents_on_new_ticket(db, t)

    return RedirectResponse("/support/my", status_code=303)


@router.get("/support/my", response_class=HTMLResponse)
def support_my(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == u["id"])
        .order_by(SupportTicket.updated_at.desc())
        .all()
    )
    return request.app.templates.TemplateResponse(
        "support_my.html",
        {"request": request, "session_user": u, "tickets": tickets, "title": "تذاكري"},
    )


@router.get("/support/ticket/{tid}", response_class=HTMLResponse)
def support_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not t or t.user_id != u["id"]:
        return RedirectResponse("/support/my", status_code=303)

    msgs = t.messages
    # علّم كمقروء للعميل
    t.unread_for_user = False
    db.commit()

    return request.app.templates.TemplateResponse(
        "support_ticket.html",
        {
            "request": request,
            "session_user": u,
            "ticket": t,
            "msgs": msgs,
            "title": f"تذكرة #{t.id}",
        },
    )


# ========== واجهة موظف خدمة الزبائن (CS) ==========

@router.get("/cs/inbox", response_class=HTMLResponse)
def cs_inbox(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    base_q = db.query(SupportTicket)

    # 🎯 التعريفات:
    # جديدة = رسائل عميل حديثة لم تُفتح بعد من أي وكيل (لا تعيين + غير مقروءة للوكيل + آخر رسالة من العميل)
    new_q = (
        base_q.filter(
            SupportTicket.status.in_(("new", "open")),
            SupportTicket.assigned_to_id.is_(None),
            SupportTicket.unread_for_agent.is_(True),
            SupportTicket.last_from == "user",
        )
        .order_by(SupportTicket.last_msg_at.desc(), SupportTicket.created_at.desc())
    )

    # قيد المراجعة = مفتوحة وعليها وكيل (معيّنة) ولم تُغلق
    in_review_q = (
        base_q.filter(
            SupportTicket.status == "open",
            SupportTicket.assigned_to_id.isnot(None),
        )
        .order_by(SupportTicket.last_msg_at.desc(), SupportTicket.updated_at.desc())
    )

    # منتهية = مغلقة
    resolved_q = (
        base_q.filter(SupportTicket.status == "resolved")
        .order_by(SupportTicket.resolved_at.desc(), SupportTicket.updated_at.desc())
    )

    data = {
        "new": new_q.all(),
        "in_review": in_review_q.all(),
        "resolved": resolved_q.all(),
    }

    return request.app.templates.TemplateResponse(
        "cs_inbox.html",
        {
            "request": request,
            "session_user": u_cs,
            "title": "CS Inbox",
            "data": data,
        },
    )

@router.get("/cs/ticket/{tid}", response_class=HTMLResponse)
def cs_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    """
    ✅ نفس منطق تحديث الجلسة كما في /cs/inbox
    """
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not t:
        return RedirectResponse("/cs/inbox", status_code=303)

    msgs = t.messages
    # علّم كمقروء للوكيل
    t.unread_for_agent = False
    db.commit()

    return request.app.templates.TemplateResponse(
        "cs_ticket.html",
        {
            "request": request,
            "session_user": u_cs,
            "ticket": t,
            "msgs": msgs,
            "title": f"تذكرة #{t.id} (CS)",
        },
    )


from fastapi import Form

@router.post("/cs/tickets/{ticket_id}/assign_self")
def cs_assign_self(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u: 
        return RedirectResponse("/login", status_code=303)
    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if t:
        # التولّي + فتح
        t.assigned_to_id = u_cs["id"]
        t.status = "open"
        t.updated_at = datetime.utcnow()
        t.unread_for_agent = False
        db.commit()

    # افتح صفحة التذكرة مباشر
    return RedirectResponse(f"/cs/ticket/{ticket_id}", status_code=303)


@router.post("/cs/tickets/{ticket_id}/resolve")
def cs_resolve(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u: 
        return RedirectResponse("/login", status_code=303)
    u_cs = _ensure_cs_session(db, request)
    if not u_cs:
        return RedirectResponse("/support/my", status_code=303)

    t = db.get(SupportTicket, ticket_id)
    if t:
        t.status = "resolved"
        t.resolved_at = datetime.utcnow()
        t.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse("/cs/inbox", status_code=303)


@router.post("/cs/ticket/{tid}/reply")
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

    # أنشئ رسالة وكيل
    m = SupportMessage(
        ticket_id=t.id,
        sender_id=u_cs["id"],
        sender_role="agent",
        body=(body or "").strip() or "(بدون نص)",
        created_at=datetime.utcnow(),
    )
    db.add(m)

    # حدّث حالة التذكرة
    t.last_msg_at = datetime.utcnow()
    t.updated_at = datetime.utcnow()
    t.last_from = "agent"
    if not t.assigned_to_id:
        t.assigned_to_id = u_cs["id"]
    if t.status in (None, "new", "resolved"):
        t.status = "open"
    t.unread_for_user = True
    t.unread_for_agent = False

    db.commit()
    return RedirectResponse(f"/cs/ticket/{t.id}", status_code=303)
