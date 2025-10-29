# داخل main.py (أو ملفك الرئيسي اللي فيه app)
from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime

# عدّل الاستيراد حسب مشروعك:
from .database import get_db
from .models import SupportTicket, User  # تأكد من المسار الصحيح

def now_utc(): 
    return datetime.utcnow()

def require_cs_user(request: Request):
    u = getattr(request.state, "session_user", None)
    ok = bool(u and (getattr(u, "is_support", False) or getattr(u, "is_mod", False) or getattr(u, "role", "") == "admin"))
    if not ok:
        raise HTTPException(status_code=403, detail="CS only")
    return u

@app.get("/cs/inbox")
def cs_inbox(request: Request, db: Session = Depends(get_db), user: User = Depends(require_cs_user)):
    q_new = (db.query(SupportTicket)
               .filter(SupportTicket.status == "new")
               .order_by(SupportTicket.last_msg_at.desc().nullslast(),
                         SupportTicket.created_at.desc()))

    q_open = (db.query(SupportTicket)
               .filter(SupportTicket.status == "open", SupportTicket.resolved_at.is_(None))
               .order_by(SupportTicket.last_msg_at.desc().nullslast(),
                         SupportTicket.updated_at.desc().nullslast(),
                         SupportTicket.created_at.desc()))

    q_done = (db.query(SupportTicket)
               .filter(or_(SupportTicket.status == "resolved", SupportTicket.resolved_at.isnot(None)))
               .order_by(SupportTicket.resolved_at.desc().nullslast(),
                         SupportTicket.updated_at.desc().nullslast(),
                         SupportTicket.last_msg_at.desc().nullslast()))

    data = {"new": q_new.all(), "in_review": q_open.all(), "resolved": q_done.all()}
    # ⬅️ اسم القالب هنا بدون مجلد فرعي:
    return request.app.state.templates.TemplateResponse("cs_inbox.html", {"request": request, "data": data})

@app.post("/cs/tickets/{tid}/resolve")
def cs_ticket_resolve(tid: int, db: Session = Depends(get_db), user: User = Depends(require_cs_user)):
    t = db.get(SupportTicket, tid)
    if not t: raise HTTPException(404, "Ticket not found")
    t.status = "resolved"
    t.resolved_at = now_utc()
    t.updated_at = now_utc()
    db.commit()
    return {"ok": True}

@app.post("/cs/tickets/{tid}/assign_self")
def cs_ticket_assign_self(tid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_cs_user)):
    t = db.get(SupportTicket, tid)
    if not t: raise HTTPException(404, "Ticket not found")
    t.assigned_to_id = user.id
    if t.status == "new":
        t.status = "open"
    if not t.last_msg_at:
        t.last_msg_at = now_utc()
    t.updated_at = now_utc()
    db.commit()
    return {"ok": True}
