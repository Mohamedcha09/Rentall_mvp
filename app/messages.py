# app/messages.py
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from .database import get_db
from .models import MessageThread, Message, User, Item

router = APIRouter()


def require_login(request: Request):
    return request.session.get("user")


def _safe_url(p: str | None, fallback: str = "/static/placeholder.svg") -> str:
    s = (p or "").strip()
    if not s:
        return fallback
    if s.lower().startswith("http://") or s.lower().startswith("https://"):
        return s
    s = s.replace("\\", "/")
    if not s.startswith("/"):
        s = "/" + s
    return s


def is_account_limited(request: Request) -> bool:
    u = request.session.get("user")
    if not u:
        return False
    return u.get("status") != "approved"


def get_first_admin(db: Session) -> User | None:
    return db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()


def is_admin_user(user: User | None) -> bool:
    return bool(user and user.role == "admin")


# ===================================================================
#                           INBOX (LIST OF THREADS)
# ===================================================================
@router.get("/messages")
def inbox(request: Request, db: Session = Depends(get_db)):
    from .models import SupportTicket

    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    uid = u["id"]

    # ============================
    #   USER MESSAGE THREADS
    # ============================
    threads = (
        db.query(MessageThread)
        .filter((MessageThread.user_a_id == uid) | (MessageThread.user_b_id == uid))
        .order_by(MessageThread.last_message_at.desc())
        .all()
    )

    # ============================
    #  SUPPORT TICKETS (ALL)
    # ============================
    support_tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == uid)
        .order_by(SupportTicket.updated_at.desc())
        .all()
    )

    tickets_count = len(support_tickets)

    # ============================
    # UNREAD COUNTS FOR THREADS
    # ============================
    thread_ids = [t.id for t in threads] or [-1]
    unread_rows = (
        db.query(Message.thread_id, func.count(Message.id))
        .filter(
            Message.thread_id.in_(thread_ids),
            Message.sender_id != uid,
            Message.is_read == False,
        )
        .group_by(Message.thread_id)
        .all()
    )
    unread_map = {tid: int(cnt) for (tid, cnt) in unread_rows}

    # ============================
    # BUILD VIEW THREADS
    # ============================
    view_threads = []
    for t in threads:
        last_msg = (
            db.query(Message)
            .filter(Message.thread_id == t.id)
            .order_by(Message.created_at.desc())
            .first()
        )
        last_text = last_msg.body if last_msg else ""

        other_id = t.user_b_id if t.user_a_id == uid else t.user_a_id
        other = db.query(User).get(other_id)

        item_title = ""
        item_image = "/static/placeholder.svg"

        if getattr(t, "item_id", None):
            item = db.query(Item).get(t.item_id)
            if item:
                item_title = item.title or ""
                if getattr(item, "image_path", None):
                    raw = item.image_path.strip()
                    if raw.startswith("http"):
                        item_image = raw
                    else:
                        item_image = "/" + raw.replace("\\", "/")

        other_avatar = _safe_url(getattr(other, "avatar_path", None))

        view_threads.append({
            "id": t.id,
            "other_fullname": f"{other.first_name} {other.last_name}" if other else "User",
            "last_message_at": t.last_message_at,
            "item_title": item_title,
            "item_image": item_image,
            "unread_count": unread_map.get(t.id, 0),
            "other_verified": bool(other.is_verified) if other else False,
            "other_avatar": other_avatar,
            "last_message_text": last_text,
        })

    return request.app.templates.TemplateResponse(
        "inbox.html",
        {
            "request": request,
            "title": "Messages",
            "threads": view_threads,
            "support_tickets": support_tickets,   # 👈 مهم جداً
            "tickets_count": tickets_count,       # 👈 الرقم
            "session_user": u,
        }
    )


# ===================================================================
#                           SUPPORT THREAD
# ===================================================================

@router.get("/messages/support")
def support_thread(request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    me = u["id"]

    admin = get_first_admin(db)
    if not admin:
        return RedirectResponse(url="/messages", status_code=303)

    thr = (
        db.query(MessageThread)
        .filter(
            ((MessageThread.user_a_id == me) & (MessageThread.user_b_id == admin.id)) |
            ((MessageThread.user_a_id == admin.id) & (MessageThread.user_b_id == me))
        )
        .filter(MessageThread.item_id.is_(None))
        .first()
    )
    if not thr:
        thr = MessageThread(
            user_a_id=me,
            user_b_id=admin.id,
            item_id=None,
            last_message_at=datetime.utcnow()
        )
        db.add(thr)
        db.commit()
        db.refresh(thr)

    return RedirectResponse(url=f"/messages/{thr.id}", status_code=303)


# ===================================================================
#                           START THREAD
# ===================================================================

@router.get("/messages/start")
def start_thread(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = 0,
    item_id: int = 0
):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    me = u["id"]

    other = db.query(User).get(user_id)
    if not other or other.id == me:
        return RedirectResponse(url="/messages", status_code=303)

    if is_account_limited(request) and not is_admin_user(other):
        return RedirectResponse(url="/messages/support", status_code=303)

    q = db.query(MessageThread).filter(
        ((MessageThread.user_a_id == me) & (MessageThread.user_b_id == other.id)) |
        ((MessageThread.user_a_id == other.id) & (MessageThread.user_b_id == me))
    )

    if item_id:
        q = q.filter(MessageThread.item_id == item_id)
    else:
        q = q.filter(MessageThread.item_id.is_(None))

    thr = q.first()
    if not thr:
        thr = MessageThread(
            user_a_id=me,
            user_b_id=other.id,
            item_id=item_id if item_id else None,
            last_message_at=datetime.utcnow()
        )
        db.add(thr)
        db.commit()
        db.refresh(thr)

    return RedirectResponse(url=f"/messages/{thr.id}", status_code=303)


# ===================================================================
#                           THREAD VIEW
# ===================================================================

@router.get("/messages/{thread_id}")
def thread_view(thread_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    thr = db.query(MessageThread).get(thread_id)
    if not thr or (u["id"] not in [thr.user_a_id, thr.user_b_id]):
        return RedirectResponse(url="/messages", status_code=303)

    other_id = thr.user_b_id if thr.user_a_id == u["id"] else thr.user_a_id
    other = db.query(User).get(other_id)

    if is_account_limited(request) and not is_admin_user(other):
        return RedirectResponse(url="/messages/support", status_code=303)

    msgs = (
        db.query(Message)
        .filter(Message.thread_id == thr.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    changed = False
    for m in msgs:
        if m.sender_id != u["id"] and not m.is_read:
            m.is_read = True
            if not m.read_at:
                m.read_at = datetime.utcnow()
            changed = True
    if changed:
        db.commit()

    item_title, item_image = "", "/static/placeholder.svg"
    if getattr(thr, "item_id", None):
        item = db.query(Item).get(thr.item_id)
        if item:
            item_title = item.title or ""
            if getattr(item, "image_path", None):
                item_image = "/" + item.image_path.replace("\\", "/")

    other_avatar = _safe_url(getattr(other, "avatar_path", None))
    item_image = _safe_url(item_image)

    return request.app.templates.TemplateResponse(
        "thread.html",
        {
            "request": request,
            "title": "Conversation",
            "thread": thr,
            "messages": msgs,
            "other": other,
            "other_avatar": other_avatar,
            "item_title": item_title,
            "item_image": item_image,
            "session_user": u,
            "account_limited": is_account_limited(request),
        }
    )


# ===================================================================
#                           SEND MESSAGE
# ===================================================================

@router.post("/messages/{thread_id}")
def thread_send(
    thread_id: int,
    request: Request,
    db: Session = Depends(get_db),
    body: str = Form(...)
):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    thr = db.query(MessageThread).get(thread_id)
    if not thr or (u["id"] not in [thr.user_a_id, thr.user_b_id]):
        return RedirectResponse(url="/messages", status_code=303)

    other_id = thr.user_b_id if thr.user_a_id == u["id"] else thr.user_a_id
    other = db.query(User).get(other_id)

    if is_account_limited(request) and not is_admin_user(other):
        return RedirectResponse(url="/messages/support", status_code=303)

    if not body.strip():
        return {"ok": True}

    msg = Message(
        thread_id=thr.id,
        sender_id=u["id"],
        body=body.strip(),
        is_read=False,
        read_at=None
    )
    db.add(msg)

    thr.last_message_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/messages/{thr.id}", status_code=303)


# ===================================================================
#                       UNREAD COUNTERS
# ===================================================================

def unread_count(user_id: int, db: Session) -> int:
    return (
        db.query(Message)
        .join(MessageThread, Message.thread_id == MessageThread.id)
        .filter(
            ((MessageThread.user_a_id == user_id) | (MessageThread.user_b_id == user_id))
            & (Message.sender_id != user_id)
            & (Message.is_read == False)
        )
        .count()
    )


def unread_grouped(user_id: int, db: Session):
    rows = (
        db.query(Message.thread_id, func.count(Message.id).label("cnt"))
        .join(MessageThread, Message.thread_id == MessageThread.id)
        .filter(
            ((MessageThread.user_a_id == user_id) | (MessageThread.user_b_id == user_id))
            & (Message.sender_id != user_id)
            & (Message.is_read == False)
        )
        .group_by(Message.thread_id)
        .all()
    )

    result = []
    for thread_id, cnt in rows:
        thr = db.query(MessageThread).get(thread_id)
        if not thr:
            continue

        other_id = thr.user_b_id if thr.user_a_id == user_id else thr.user_a_id
        other = db.query(User).get(other_id)
        other_name = f"{other.first_name} {other.last_name}" if other else "User"

        item_title = ""
        if getattr(thr, "item_id", None):
            item = db.query(Item).get(thr.item_id)
            if item and item.title:
                item_title = item.title

        result.append({
            "thread_id": thread_id,
            "count": int(cnt),
            "other_name": other_name,
            "item_title": item_title,
            "other_verified": bool(other.is_verified) if other else False,
        })

    return result


@router.get("/api/unread_summary")
def api_unread_summary(request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return JSONResponse({"total": 0, "threads": []})

    return JSONResponse({
        "total": unread_count(u["id"], db),
        "threads": unread_grouped(u["id"], db)
    })


# ===================================================================
#                       TYPING INDICATOR
# ===================================================================

from datetime import datetime, timedelta
typing_state = {}   # { thread_id: { user_id: datetime_expire } }

@router.post("/messages/{thread_id}/typing")
def set_typing(thread_id: int, request: Request, db: Session = Depends(get_db)):
    session_user = request.session.get("user")
    if not session_user:
        return {"ok": False}

    uid = session_user["id"]

    if thread_id not in typing_state:
        typing_state[thread_id] = {}

    typing_state[thread_id][uid] = datetime.utcnow() + timedelta(seconds=3)
    return {"ok": True}


@router.get("/messages/{thread_id}/typing_status")
def typing_status(thread_id: int, request: Request):
    session_user = request.session.get("user")
    if not session_user:
        return {"typing": False}

    uid = session_user["id"]

    if thread_id not in typing_state:
        return {"typing": False}

    now = datetime.utcnow()

    for user_id, expires_at in typing_state[thread_id].items():
        if user_id != uid and expires_at > now:
            return {"typing": True}

    return {"typing": False}


@router.get("/messages/{thread_id}/poll")
def poll_messages(thread_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return {"messages": []}

    last_id = int(request.query_params.get("after", 0))

    rows = (
        db.query(Message)
        .filter(Message.thread_id == thread_id, Message.id > last_id)
        .order_by(Message.id.asc())
        .all()
    )

    return {
        "messages": [
            {
                "id": m.id,
                "body": m.body,
                "time": m.created_at.strftime("%H:%M"),
                "from_me": (m.sender_id == u["id"]),
            }
            for m in rows
        ]
    }
