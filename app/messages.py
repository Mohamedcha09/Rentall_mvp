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

# NEW: هل حساب المستخدم مقيد (ليس approved)؟
def is_account_limited(request: Request) -> bool:
    u = request.session.get("user")
    if not u:
        return False
    return u.get("status") != "approved"

# NEW: أدوات مساعدة للأدمِن
def get_first_admin(db: Session) -> User | None:
    return db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()

def is_admin_user(user: User | None) -> bool:
    return bool(user and user.role == "admin")


@router.get("/messages")
def inbox(request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    uid = u["id"]

    # كل خيوط المستخدم
    threads = (
        db.query(MessageThread)
        .filter((MessageThread.user_a_id == uid) | (MessageThread.user_b_id == uid))
        .order_by(MessageThread.last_message_at.desc())
        .all()
    )

    # لو الحساب مقيد: أعرض فقط خيوط الدعم مع الأدمِن
    if is_account_limited(request):
        filtered = []
        for t in threads:
            other_id = t.user_b_id if t.user_a_id == uid else t.user_a_id
            other = db.query(User).get(other_id)
            if is_admin_user(other):
                filtered.append(t)
        threads = filtered

    # IDs الخيوط لحساب غير المقروء
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

    view_threads = []
    for t in threads:
        other_id = t.user_b_id if t.user_a_id == uid else t.user_a_id
        other = db.query(User).get(other_id)

        # بيانات العنصر المرتبط بالخيط (إن وجد)
        item_title, item_image = "", "/static/placeholder.svg"
        if getattr(t, "item_id", None):
            item = db.query(Item).get(t.item_id)
            if item:
                item_title = item.title or ""
                if getattr(item, "image_path", None):
                    item_image = "/" + item.image_path.replace("\\", "/")

        view_threads.append({
            "id": t.id,
            "other_fullname": f"{other.first_name} {other.last_name}" if other else "مستخدم",
            "last_message_at": t.last_message_at,
            "item_title": item_title,
            "item_image": item_image,
            "unread_count": unread_map.get(t.id, 0),
            "other_verified": bool(other.is_verified) if other else False,  # ✅ موجود
        })

    return request.app.templates.TemplateResponse(
        "inbox.html",
        {
            "request": request,
            "title": "الرسائل",
            "threads": view_threads,
            "session_user": u,
            "account_limited": is_account_limited(request),  # NEW
        }
    )

# NEW: خيط دعم مع الأدمِن
@router.get("/messages/support")
def support_thread(request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    me = u["id"]

    admin = get_first_admin(db)
    if not admin:
        # لو ما عندنا أدمِن أصلاً نرجّع لصندوق الرسائل
        return RedirectResponse(url="/messages", status_code=303)

    # ابحث عن خيط موجود بيني وبين الأدمِن (بدون عنصر)
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
def start_thread(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = 0,
    item_id: int = 0
):
    """
    يبدأ خيط محادثة بين المستخدم الحالي و user_id،
    ويُثبِّت الخيط على item_id إن كان مُرسلًا.
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)
    me = u["id"]

    other = db.query(User).get(user_id)
    if not other or other.id == me:
        return RedirectResponse(url="/messages", status_code=303)

    # NEW: لو الحساب مقيد ولا يراسل أدمِن → حوّله لدعم
    if is_account_limited(request) and not is_admin_user(other):
        return RedirectResponse(url="/messages/support", status_code=303)

    # ابحث عن خيط لنفس الثنائي ولنفس الـ item_id (أو NULL)
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


@router.get("/messages/{thread_id}")
def thread_view(thread_id: int, request: Request, db: Session = Depends(get_db)):
    """
    عرض محادثة معينة + وسم الرسائل الواردة كمقروءة.
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    thr = db.query(MessageThread).get(thread_id)
    if not thr or (u["id"] not in [thr.user_a_id, thr.user_b_id]):
        return RedirectResponse(url="/messages", status_code=303)

    # NEW: لو الحساب مقيد وتكلّم مع غير أدمِن → حوّله للدعم
    other_id = thr.user_b_id if thr.user_a_id == u["id"] else thr.user_a_id
    other = db.query(User).get(other_id)
    if is_account_limited(request) and not is_admin_user(other):
        return RedirectResponse(url="/messages/support", status_code=303)

    # اجلب الرسائل الأقدم فالأحدث
    msgs = (
        db.query(Message)
        .filter(Message.thread_id == thr.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    # علّم رسائل الطرف الآخر كمقروءة
    changed = False
    for m in msgs:
        if m.sender_id != u["id"] and not m.is_read:
            m.is_read = True
            if not m.read_at:
                m.read_at = datetime.utcnow()
            changed = True
    if changed:
        db.commit()

    # معلومات العنصر (إن وجد)
    item_title, item_image = "", "/static/placeholder.svg"
    if getattr(thr, "item_id", None):
        item = db.query(Item).get(thr.item_id)
        if item:
            item_title = item.title or ""
            if getattr(item, "image_path", None):
                item_image = "/" + item.image_path.replace("\\", "/")

    return request.app.templates.TemplateResponse(
        "thread.html",
        {
            "request": request,
            "title": "محادثة",
            "thread": thr,
            "messages": msgs,
            "other": other,
            "item_title": item_title,
            "item_image": item_image,
            "session_user": u,
            "account_limited": is_account_limited(request),  # NEW: للقالب
        }
    )


@router.post("/messages/{thread_id}")
def thread_send(
    thread_id: int,
    request: Request,
    db: Session = Depends(get_db),
    body: str = Form(...)
):
    """
    إرسال رسالة داخل خيط محدد.
    """
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    thr = db.query(MessageThread).get(thread_id)
    if not thr or (u["id"] not in [thr.user_a_id, thr.user_b_id]):
        return RedirectResponse(url="/messages", status_code=303)

    # NEW: منع الإرسال لغير الأدمِن لو الحساب مقيد
    other_id = thr.user_b_id if thr.user_a_id == u["id"] else thr.user_a_id
    other = db.query(User).get(other_id)
    if is_account_limited(request) and not is_admin_user(other):
        return RedirectResponse(url="/messages/support", status_code=303)

    if not body.strip():
        return RedirectResponse(url=f"/messages/{thr.id}", status_code=303)

    # إنشاء الرسالة
    msg = Message(
        thread_id=thr.id,
        sender_id=u["id"],
        body=body.strip(),
        is_read=False,
        read_at=None
    )
    db.add(msg)

    # تحديث آخر وقت تواصل
    thr.last_message_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/messages/{thr.id}", status_code=303)


def unread_count(user_id: int, db: Session) -> int:
    """
    عدد الرسائل غير المقروءة للمستخدم عبر كل الخيوط.
    """
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
    """
    إرجاع (thread_id, count) للمحادثات التي تحتوي رسائل غير مقروءة،
    مع اسم الطرف الآخر وعنوان العنصر (إن وجد).
    """
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
        other_name = f"{other.first_name} {other.last_name}" if other else "مستخدم"

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
            "other_verified": bool(other.is_verified) if other else False,  # ✅ بقيت
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
