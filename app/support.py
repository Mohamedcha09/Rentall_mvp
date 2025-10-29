# app/support.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from .database import get_db
from .models import SupportTicket, SupportMessage, User
from datetime import datetime

# ✅ استيراد دالة الإشعارات الداخلية
from .notifications_api import push_notification

router = APIRouter()

# ===== Helpers =====
def _require_login(request: Request):
    u = request.session.get("user")
    if not u:
        return None
    return u

def _require_cs(request: Request):
    u = _require_login(request)
    if not u or not u.get("is_support", False):
        return None
    return u

# ✅ دالة ترسل إشعارًا لكل موظف CS عند فتح تذكرة جديدة
def _notify_support_agents_on_new_ticket(db: Session, ticket: SupportTicket):
    agents = (
        db.query(User)
        .filter(User.is_support == True, User.status == "approved")
        .all()
    )
    # لو عندك صفحة تفاصيل تذكرة للـ CS استخدم الرابط المباشر:
    url = f"/cs/ticket/{ticket.id}"  # بدّلها إلى "/cs/inbox" لو تفضّل الصندوق العام
    title = "تذكرة دعم جديدة"
    body  = f"#{ticket.id} — {ticket.subject or ''}"
    for ag in agents:
        try:
            push_notification(
                db, ag.id,
                title,
                body,
                url,
                "ticket_new"
            )
        except Exception:
            # ما نوقف العملية لو فشل إشعار واحد
            pass

# ========== واجهة العميل ==========
@router.get("/support/new", response_class=HTMLResponse)
def support_new(request: Request):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    return request.app.templates.TemplateResponse(
        "support_new.html",
        {"request": request, "session_user": u, "title": "مراسلة الدعم"}
    )

@router.post("/support/new")
def support_new_post(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    form = request._form  # Starlette يحفظ آخر فورم — لو ما تشتغل عندك، بدّلها ب await request.form()
    if form is None:
        # fallback
        import anyio
        async def _read_form():
            f = await request.form()
            return f
        form = anyio.from_thread.run(_read_form)

    subject = form.get("subject", "").strip() if form else ""
    body    = form.get("body", "").strip() if form else ""

    if not subject:
        subject = "بدون عنوان"

    t = SupportTicket(
        user_id=u["id"], subject=subject, status="open",
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        last_from="user", unread_for_agent=True, unread_for_user=False
    )
    db.add(t); db.flush()

    m = SupportMessage(
        ticket_id=t.id, sender_id=u["id"], sender_role="user",
        body=body or "(بدون نص)", created_at=datetime.utcnow()
    )
    db.add(m); db.commit()

    # ✅ بعد إنشاء التذكرة بنجاح: أرسل إشعارات للـ CS
    _notify_support_agents_on_new_ticket(db, t)

    return RedirectResponse(f"/support/my", status_code=303)

@router.get("/support/my", response_class=HTMLResponse)
def support_my(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    tickets = db.query(SupportTicket).filter(SupportTicket.user_id == u["id"])\
                .order_by(SupportTicket.updated_at.desc()).all()
    return request.app.templates.TemplateResponse(
        "support_my.html",
        {"request": request, "session_user": u, "tickets": tickets, "title": "تذاكري"}
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
        {"request": request, "session_user": u, "ticket": t, "msgs": msgs, "title": f"تذكرة #{t.id}"}
    )

# ========== واجهة موظف خدمة الزبائن (CS) ==========
@router.get("/cs/inbox", response_class=HTMLResponse)
def cs_inbox(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    if not u.get("is_support", False):
        # ✅ مسجل دخول لكن ليس CS → رجّعه لتذاكره بدل صفحة login
        return RedirectResponse("/support/my", status_code=303)

    tickets = db.query(SupportTicket).order_by(SupportTicket.updated_at.desc()).all()
    return request.app.templates.TemplateResponse(
        "cs_inbox.html",
        {"request": request, "session_user": u, "tickets": tickets, "title": "صندوق خدمة الزبائن"}
    )


@router.get("/cs/ticket/{tid}", response_class=HTMLResponse)
def cs_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    if not u.get("is_support", False):
        # ✅ مسجل دخول لكن ليس CS
        return RedirectResponse("/support/my", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not t:
        return RedirectResponse("/cs/inbox", status_code=303)
    msgs = t.messages
    t.unread_for_agent = False
    db.commit()
    return request.app.templates.TemplateResponse(
        "cs_ticket.html",
        {"request": request, "session_user": u, "ticket": t, "msgs": msgs, "title": f"تذكرة #{t.id} (CS)"}
    )
