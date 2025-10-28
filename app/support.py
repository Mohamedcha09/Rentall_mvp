# app/support.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional

from .database import get_db
from .models import User, SupportTicket, SupportMessage

router = APIRouter()

def _current_user(request: Request, db: Session) -> Optional[User]:
    sess = request.session.get("user")
    if not sess:
        return None
    return db.query(User).filter(User.id == int(sess.get("id", 0))).first()

def _is_agent(u: Optional[User]) -> bool:
    if not u:
        return False
    role = (u.role or "").lower()
    return (role == "admin") or bool(getattr(u, "is_mod", False))

# ===== واجهة المستخدم =====
@router.get("/support")
def support_home(request: Request, db: Session = Depends(get_db)):
    u = _current_user(request, db)
    if not u:
        return RedirectResponse("/login", status_code=303)
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == u.id)
        .order_by(SupportTicket.updated_at.desc())
        .all()
    )
    return request.app.templates.TemplateResponse(
        "support_inbox.html",
        {"request": request, "session_user": request.session.get("user"),
         "tickets": tickets, "is_agent": _is_agent(u)}
    )

@router.post("/support/start")
def support_start(request: Request, db: Session = Depends(get_db),
                  subject: str = Form(...), body: str = Form(...)):
    u = _current_user(request, db)
    if not u:
        return RedirectResponse("/login", status_code=303)

    t = SupportTicket(
        user_id=u.id,
        subject=(subject or "").strip()[:200],
        status="open",
        last_from="user",
        unread_for_user=False,
        unread_for_agent=True,
    )
    db.add(t); db.flush()
    m = SupportMessage(ticket_id=t.id, sender_id=u.id, sender_role="user", body=(body or "").strip())
    db.add(m); db.commit()
    return RedirectResponse(f"/support/t/{t.id}", status_code=303)

@router.get("/support/t/{tid}")
def support_chat(request: Request, tid: int, db: Session = Depends(get_db)):
    u = _current_user(request, db)
    if not u:
        return RedirectResponse("/login", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if (not t) or (t.user_id != u.id and not _is_agent(u)):
        return RedirectResponse("/support", status_code=303)

    # إزالة شارة غير مقروء للطرف المناسب
    if _is_agent(u):
        if t.unread_for_agent:
            t.unread_for_agent = False
            db.add(t); db.commit()
    else:
        if t.unread_for_user:
            t.unread_for_user = False
            db.add(t); db.commit()

    return request.app.templates.TemplateResponse(
        "support_chat.html",
        {"request": request, "session_user": request.session.get("user"),
         "ticket": t, "messages": t.messages, "is_agent": _is_agent(u)}
    )

@router.post("/support/t/{tid}/send")
def support_send(request: Request, tid: int, db: Session = Depends(get_db),
                 body: str = Form(...)):
    u = _current_user(request, db)
    if not u:
        return RedirectResponse("/login", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if (not t) or (t.user_id != u.id and not _is_agent(u)):
        return RedirectResponse("/support", status_code=303)

    sender_role = "agent" if _is_agent(u) else "user"
    msg = SupportMessage(ticket_id=tid, sender_id=u.id, sender_role=sender_role, body=(body or "").strip())
    db.add(msg)

    if sender_role == "user":
        t.last_from = "user"
        t.unread_for_agent = True
    else:
        if not t.agent_id:
            t.agent_id = u.id
            t.status = "assigned"
        t.last_from = "agent"
        t.unread_for_user = True

    db.add(t); db.commit()
    return RedirectResponse(f"/support/t/{t.id}", status_code=303)

# ===== للوكيل/الأدمن =====
@router.get("/admin/support")
def admin_support_inbox(request: Request, db: Session = Depends(get_db)):
    u = _current_user(request, db)
    if not _is_agent(u):
        return RedirectResponse("/login", status_code=303)

    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.status.in_(["open", "assigned"]))
        .order_by(SupportTicket.unread_for_agent.desc(), SupportTicket.updated_at.desc())
        .all()
    )
    return request.app.templates.TemplateResponse(
        "support_inbox.html",
        {"request": request, "session_user": request.session.get("user"),
         "tickets": tickets, "is_agent": True}
    )

@router.post("/admin/support/claim/{tid}")
def admin_support_claim(request: Request, tid: int, db: Session = Depends(get_db)):
    u = _current_user(request, db)
    if not _is_agent(u):
        return RedirectResponse("/login", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not t:
        return RedirectResponse("/admin/support", status_code=303)

    t.agent_id = u.id
    t.status = "assigned"
    db.add(t); db.commit()
    return RedirectResponse(f"/support/t/{t.id}", status_code=303)

@router.post("/admin/support/close/{tid}")
def admin_support_close(request: Request, tid: int, db: Session = Depends(get_db)):
    u = _current_user(request, db)
    if not _is_agent(u):
        return RedirectResponse("/login", status_code=303)

    t = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not t:
        return RedirectResponse("/admin/support", status_code=303)

    t.status = "closed"
    db.add(t); db.commit()
    return RedirectResponse("/admin/support", status_code=303)

@router.get("/api/support/unread_for_agent")
def unread_for_agent_api(request: Request, db: Session = Depends(get_db)):
    u = _current_user(request, db)
    if not _is_agent(u):
        return JSONResponse({"count": 0})
    cnt = db.query(SupportTicket).filter(SupportTicket.unread_for_agent == True).count()  # noqa: E712
    return JSONResponse({"count": cnt})
