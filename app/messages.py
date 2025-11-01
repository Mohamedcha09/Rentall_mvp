# app/messages.py
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, desc
from datetime import datetime

from .database import get_db
from .models import MessageThread, Message, User, Item

router = APIRouter()


# -----------------------------
# Helpers (جلسة/أذونات)
# -----------------------------
def require_login(request: Request):
    return request.session.get("user")

def is_account_limited(request: Request) -> bool:
    u = request.session.get("user")
    if not u:
        return False
    return u.get("status") != "approved"

def get_first_admin(db: Session) -> User | None:
    return db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()

def is_admin_user(user: User | None) -> bool:
    return bool(user and user.role == "admin")


# -----------------------------
# Helpers (استعلامات/تهيئة عرض)
# -----------------------------
def _other_user_of(thr: MessageThread, my_id: int, db: Session) -> User | None:
    other_id = thr.user_b_id if thr.user_a_id == my_id else thr.user_a_id
    return db.query(User).get(other_id)

def _threads_for(db: Session, uid: int):
    return (
        db.query(MessageThread)
        .filter(or_(MessageThread.user_a_id == uid, MessageThread.user_b_id == uid))
        .order_by(desc(MessageThread.last_message_at))
        .all()
    )

def _filter_threads_for_account_limit(threads, uid: int, db: Session, limited: bool):
    """لو الحساب محدود: أبقِ فقط الخيوط مع الأدمِن."""
    if not limited:
        return threads
    filtered = []
    for t in threads:
        other = _other_user_of(t, uid, db)
        if is_admin_user(other):
            filtered.append(t)
    return filtered

def _item_info(db: Session, item_id: int | None):
    title, image = "", "/static/placeholder.svg"
    if item_id:
        item = db.query(Item).get(item_id)
        if item:
            title = item.title or ""
            if getattr(item, "image_path", None):
                image = "/" + item.image_path.replace("\\", "/")
    return title, image

def _unread_map_for(uid: int, thread_ids: list[int], db: Session) -> dict[int, int]:
    if not thread_ids:
        return {}
    rows = (
        db.query(Message.thread_id, func.count(Message.id))
        .filter(
            Message.thread_id.in_(thread_ids),
            Message.sender_id != uid,
            Message.is_read == False,
        )
        .group_by(Message.thread_id)
        .all()
    )
    return {tid: int(cnt) for (tid, cnt) in rows}

def _serialize_thread_row(t: MessageThread, uid: int, db: Session, unread_map: dict[int, int]):
    other = _other_user_of(t, uid, db)
    item_title, item_image = _item_info(db, getattr(t, "item_id", None))
    full = f"{other.first_name} {other.last_name}".strip() if other else "مستخدم"
    return {
        "id": t.id,
        "other_fullname": full or "مستخدم",
        "last_message_at": t.last_message_at,
        "item_title": item_title,
        "item_image": item_image,
        "unread_count": unread_map.get(t.id, 0),
        "other_verified": bool(other.is_verified) if other else False,
        "other_user": other,  # مفيد لو احتجته في القالب
    }

def _serialize_threads_list(threads, uid: int, db: Session):
    ids = [t.id for t in threads] or [-1]
    unread_map = _unread_map_for(uid, ids, db)
    return [_serialize_thread_row(t, uid, db, unread_map) for t in threads]

def _serialize_thread_with_messages(thr: MessageThread, uid: int, db: Session):
    """خيط للعرض في العمود الأيمن + رسائله (objects) ليستفيد القالب منها مباشرة."""
    if not thr:
        return None
    other = _other_user_of(thr, uid, db)
    item_title, item_image = _item_info(db, getattr(thr, "item_id", None))

    # اجلب الرسائل الأقدم فالأحدث
    msgs = (
        db.query(Message)
        .filter(Message.thread_id == thr.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    return {
        "id": thr.id,
        "other_user": other,
        "other_fullname": (f"{other.first_name} {other.last_name}".strip() if other else "مستخدم") or "مستخدم",
        "item_title": item_title,
        "item_image": item_image,
        "messages": msgs,  # القالب يستخدم m.sender.first_name … إلخ
        "last_message_at": thr.last_message_at,
    }


# -----------------------------
# Routes: كلاهما يعيدان نفس القالب messages.html
# -----------------------------
@router.get("/messages")
def inbox(request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    uid = u["id"]

    limited = is_account_limited(request)

    threads_q = _threads_for(db, uid)
    threads_q = _filter_threads_for_account_limit(threads_q, uid, db, limited)
    view_threads = _serialize_threads_list(threads_q, uid, db)

    # نعيد نفس القالب بنمط واتساب (قائمة يسار + يمين)
    return request.app.templates.TemplateResponse(
        "messages.html",
        {
            "request": request,
            "title": "الرسائل",
            "threads": view_threads,   # قائمة اليسار
            "thread": None,            # القالب يمكنه اختيار أول واحد تلقائيًا
            "session_user": u,
            "account_limited": limited,
        }
    )


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


@router.get("/messages/start")
def start_thread(request: Request, db: Session = Depends(get_db), user_id: int = 0, item_id: int = 0):
    """ابدأ خيط بين المستخدم الحالي و user_id (وربط item إن وجد)."""
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
            user_a_id=me, user_b_id=other.id,
            item_id=item_id if item_id else None,
            last_message_at=datetime.utcnow()
        )
        db.add(thr)
        db.commit()
        db.refresh(thr)

    return RedirectResponse(url=f"/messages/{thr.id}", status_code=303)


@router.get("/messages/{thread_id}")
def thread_view(thread_id: int, request: Request, db: Session = Depends(get_db)):
    """
    عرض محادثة معيّنة داخل **نفس القالب** (يسار+يمين)،
    مع وسم رسائل الطرف الآخر كمقروءة.
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    uid = u["id"]

    thr = db.query(MessageThread).get(thread_id)
    if not thr or (uid not in [thr.user_a_id, thr.user_b_id]):
        return RedirectResponse(url="/messages", status_code=303)

    # منع الوصول لغير الأدمِن إن كان الحساب محدود
    other = _other_user_of(thr, uid, db)
    if is_account_limited(request) and not is_admin_user(other):
        return RedirectResponse(url="/messages/support", status_code=303)

    # وسم رسائل الطرف الآخر كمقروءة
    msgs = (
        db.query(Message)
        .filter(Message.thread_id == thr.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    changed = False
    for m in msgs:
        if m.sender_id != uid and not m.is_read:
            m.is_read = True
            if not m.read_at:
                m.read_at = datetime.utcnow()
            changed = True
    if changed:
        db.commit()

    # حضّر قائمة اليسار + الخيط الحالي
    limited = is_account_limited(request)
    threads_q = _filter_threads_for_account_limit(_threads_for(db, uid), uid, db, limited)
    view_threads = _serialize_threads_list(threads_q, uid, db)
    current = _serialize_thread_with_messages(thr, uid, db)

    # ❗️نفس القالب messages.html (وليس inbox.html / thread.html)
    return request.app.templates.TemplateResponse(
        "messages.html",
        {
            "request": request,
            "title": "الرسائل",
            "threads": view_threads,
            "thread": current,          # سيظهر في عمود اليمين داخل نفس الصفحة
            "session_user": u,
            "account_limited": limited,
        }
    )


@router.post("/messages/{thread_id}")
def thread_send(thread_id: int, request: Request, db: Session = Depends(get_db), body: str = Form(...)):
    """إرسال رسالة داخل خيط محدّد، ثم العودة لنفس القالب."""
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    uid = u["id"]

    thr = db.query(MessageThread).get(thread_id)
    if not thr or (uid not in [thr.user_a_id, thr.user_b_id]):
        return RedirectResponse(url="/messages", status_code=303)

    other = _other_user_of(thr, uid, db)
    if is_account_limited(request) and not is_admin_user(other):
        return RedirectResponse(url="/messages/support", status_code=303)

    if not body.strip():
        return RedirectResponse(url=f"/messages/{thr.id}", status_code=303)

    msg = Message(
        thread_id=thr.id,
        sender_id=uid,
        body=body.strip(),
        is_read=False,
        read_at=None
    )
    db.add(msg)
    thr.last_message_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/messages/{thr.id}", status_code=303)


# -----------------------------
# APIs للإشعارات (كما كانت)
# -----------------------------
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
        other_name = f"{other.first_name} {other.last_name}".strip() if other else "مستخدم"
        item_title = ""
        if getattr(thr, "item_id", None):
            item = db.query(Item).get(thr.item_id)
            if item and item.title:
                item_title = item.title
        result.append({
            "thread_id": thread_id,
            "count": int(cnt),
            "other_name": other_name or "مستخدم",
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
