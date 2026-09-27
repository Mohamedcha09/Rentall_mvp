# app/messages.py
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, lazyload, selectinload
from sqlalchemy import func

from .database import get_db
from .message_attachments import (
    allowed_attachment_accept_value,
    cleanup_staged_message_attachments,
    max_attachment_bytes,
    max_attachments_per_message,
    max_voice_bytes,
    message_attachment_path,
    persist_staged_message_attachments,
    remove_saved_message_attachment_files,
    serialize_message_attachment,
    stage_message_attachments,
)
from .models import MessageThread, Message, MessageAttachment, User, Item, SupportTicket
from .presence import user_presence
from .support_ai import get_or_create_csrf_token, require_csrf, validate_client_message_id

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
    # Email verification currently places normal users in the `active` state,
    # while admin approval uses `approved`.  Both are established account
    # states and may use the existing direct-message flow.
    status = str(u.get("status") or "").strip().lower()
    role = str(u.get("role") or "").strip().lower()
    return role != "admin" and status not in {"active", "approved"}


def get_first_admin(db: Session) -> User | None:
    return db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()


def is_admin_user(user: User | None) -> bool:
    return bool(user and user.role == "admin")


def _thread_for_member(
    db: Session,
    request: Request,
    thread_id: int,
    *,
    api: bool = False,
) -> tuple[dict, MessageThread, User]:
    """Load a direct conversation only for a real participant.

    Polling, typing, private media, and presence all use this same gate.  This
    closes the old gap where a logged-in user could poll a guessed thread id.
    """
    session_user = require_login(request)
    if not session_user:
        raise HTTPException(status_code=401, detail="Login required")
    thread = db.get(MessageThread, thread_id)
    try:
        user_id = int(session_user.get("id")) if isinstance(session_user, dict) else None
    except (TypeError, ValueError):
        user_id = None
    if not thread or user_id not in (thread.user_a_id, thread.user_b_id):
        # Keep absent and unauthorized direct threads indistinguishable.
        raise HTTPException(status_code=404, detail="Conversation not found")
    other_id = thread.user_b_id if thread.user_a_id == user_id else thread.user_a_id
    other = db.get(User, other_id)
    if not other:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if is_account_limited(request) and not is_admin_user(other):
        raise HTTPException(status_code=403, detail="Messaging is currently unavailable")
    return session_user, thread, other


def _serialize_message(message: Message, *, viewer_id: int) -> dict[str, object]:
    created_at = message.created_at
    return {
        "id": message.id,
        "body": message.body or "",
        "time": created_at.strftime("%I:%M %p").lstrip("0") if created_at else "",
        "date_key": created_at.strftime("%Y-%m-%d") if created_at else "",
        "date_label": created_at.strftime("%b %d, %Y") if created_at else "",
        "created_at": created_at.isoformat() if created_at else None,
        "from_me": message.sender_id == viewer_id,
        "is_read": bool(message.is_read),
        "attachments": [
            serialize_message_attachment(attachment, thread_id=message.thread_id)
            for attachment in (message.attachments or [])
        ],
    }


# ===================================================================
#                           INBOX (LIST OF THREADS)
# ===================================================================
@router.get("/messages")
def inbox(request: Request, db: Session = Depends(get_db)):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    uid = u["id"]

    # ========= threads العادية =========
    threads = (
        db.query(MessageThread)
        .filter((MessageThread.user_a_id == uid) | (MessageThread.user_b_id == uid))
        .order_by(MessageThread.last_message_at.desc())
        .all()
    )

    # Resolve the other participant once for all threads.  The previous loop
    # queried a User for every thread, then repeated that lookup when building
    # the template payload.
    other_ids = {
        t.user_b_id if t.user_a_id == uid else t.user_a_id
        for t in threads
    }
    users_by_id = {}
    if other_ids:
        users_by_id = {
            user.id: user
            for user in db.query(User).filter(User.id.in_(other_ids)).all()
        }

    account_limited = is_account_limited(request)
    if account_limited:
        threads = [
            t
            for t in threads
            if is_admin_user(
                users_by_id.get(
                    t.user_b_id if t.user_a_id == uid else t.user_a_id
                )
            )
        ]

    thread_ids = [t.id for t in threads]
    unread_map = {}
    if thread_ids:
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

    # Select the newest message for every displayed thread in one query.
    # The row-number window works on PostgreSQL and supported SQLite versions,
    # and avoids one ORDER BY/LIMIT query per conversation.
    last_text_by_thread = {}
    if thread_ids:
        ranked_messages = (
            db.query(
                Message.thread_id.label("thread_id"),
                Message.body.label("body"),
                func.row_number()
                .over(
                    partition_by=Message.thread_id,
                    order_by=(Message.created_at.desc(), Message.id.desc()),
                )
                .label("row_number"),
            )
            .filter(Message.thread_id.in_(thread_ids))
            .subquery()
        )
        last_text_by_thread = {
            row.thread_id: row.body or ""
            for row in db.query(ranked_messages.c.thread_id, ranked_messages.c.body)
            .filter(ranked_messages.c.row_number == 1)
            .all()
        }

    item_ids = {t.item_id for t in threads if getattr(t, "item_id", None)}
    items_by_id = {}
    if item_ids:
        items_by_id = {
            item.id: item
            for item in db.query(Item).filter(Item.id.in_(item_ids)).all()
        }

    # ========= تذاكر الشات بوت فقط (channel='chatbot') =========
    chatbot_tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == uid)
        .filter(SupportTicket.channel == "chatbot")   # 👈 مهم: لا نأخذ legacy
        .order_by(SupportTicket.updated_at.desc())
        .all()
    )
    tickets_count = len(chatbot_tickets)

    # Historical tickets remain visible below.  The top-level “SEVOR Support”
    # row is deliberately a separate POST action that closes any of these
    # live chatbot tickets and starts one clean session (implemented by
    # /chatbot/support/new), rather than linking to this current ticket.
    active_chatbot_ticket = next(
        (
            ticket
            for ticket in chatbot_tickets
            if str(getattr(ticket, "status", "")).lower() not in {"resolved", "closed"}
        ),
        None,
    )

    # ========= بناء قائمة threads للـ HTML =========
    view_threads = []
    for t in threads:
        last_text = last_text_by_thread.get(t.id, "")

        other_id = t.user_b_id if t.user_a_id == uid else t.user_a_id
        other = users_by_id.get(other_id)

        item_title = ""
        item_image = "/static/placeholder.svg"

        if getattr(t, "item_id", None):
            item = items_by_id.get(t.item_id)
            if item:
                item_title = item.title or ""
                if getattr(item, "image_path", None):
                    raw = item.image_path.strip()
                    if raw.startswith("http://") or raw.startswith("https://"):
                        item_image = raw
                    else:
                        raw = raw.replace("\\", "/")
                        if not raw.startswith("/"):
                            raw = "/" + raw
                        item_image = raw

        other_avatar = _safe_url(getattr(other, "avatar_path", None))
        item_image   = _safe_url(item_image)

        other_verified   = bool(other.is_verified) if other else False
        other_created_iso = other.created_at.isoformat() if (other and other.created_at) else ""

        view_threads.append({
            "id": t.id,
            "other_fullname": f"{other.first_name} {other.last_name}" if other else "User",
            "last_message_at": t.last_message_at,
            "item_title": item_title,
            "item_image": item_image,
            "unread_count": unread_map.get(t.id, 0),
            "other_verified": other_verified,
            "other_avatar": other_avatar,
            "other_created_iso": other_created_iso,
            "last_message_text": last_text,
            # Presentation-only marker for the existing direct SEVOR support thread.
            # It does not alter the thread query, permissions, or support workflow.
            "is_support_thread": bool(other and is_admin_user(other) and not getattr(t, "item_id", None)),
        })

    return request.app.templates.TemplateResponse(
        request=request,
        name="inbox.html",
        context={
            "request": request,
            "title": "Messages",
            "threads": view_threads,
            "chatbot_tickets": chatbot_tickets,  # 👈 يُستخدم في التمبلت
            "active_chatbot_ticket": active_chatbot_ticket,
            "tickets_count": tickets_count,      # 👈 للبادج
            "session_user": u,
            "chatbot_csrf_token": get_or_create_csrf_token(request),
            "account_limited": account_limited,
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

    # A presentation cursor lets the existing polling channel return only
    # read-state changes that happened after this server-rendered snapshot.
    # It does not alter the Message lifecycle or schema.
    receipt_cursor = datetime.utcnow()

    msgs = (
        db.query(Message)
        .options(selectinload(Message.attachments))
        .filter(Message.thread_id == thr.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
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
                # Keep hosted listing images intact; only local paths need a leading slash.
                raw = item.image_path.strip()
                if raw.startswith("http://") or raw.startswith("https://"):
                    item_image = raw
                else:
                    raw = raw.replace("\\", "/")
                    if not raw.startswith("/"):
                        raw = "/" + raw
                    item_image = raw

    other_avatar = _safe_url(getattr(other, "avatar_path", None))
    item_image = _safe_url(item_image)

    return request.app.templates.TemplateResponse(
        request=request,
        name="thread.html",
        context={
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
            "receipt_cursor": receipt_cursor.isoformat(),
            "csrf_token": get_or_create_csrf_token(request),
            "client_message_id": uuid.uuid4().hex,
            "attachment_accept": allowed_attachment_accept_value(),
            "max_attachment_bytes": max_attachment_bytes(),
            "max_voice_bytes": max_voice_bytes(),
            "max_attachments": max_attachments_per_message(),
            "other_presence": user_presence(db, other_id),
            # This only controls the shared-shell presentation for the
            # focused conversation; route and message behavior stay intact.
            "focused_conversation": True,
        }
    )


# ===================================================================
#                           SEND MESSAGE
# ===================================================================

async def _close_uploads(
    uploads: list[UploadFile] | None,
    voice_upload: UploadFile | None,
) -> None:
    for upload in [*(uploads or []), *([voice_upload] if voice_upload else [])]:
        try:
            await upload.close()
        except Exception:
            pass


async def _create_direct_message(
    db: Session,
    *,
    request: Request,
    thread: MessageThread,
    sender: User,
    body: str,
    uploads: list[UploadFile] | None,
    voice_upload: UploadFile | None,
    voice_duration_ms: str | None,
    client_message_id: str | None,
) -> tuple[Message, bool]:
    """Persist one idempotent direct message and its private media atomically."""
    message_key = validate_client_message_id(client_message_id)
    if message_key:
        existing = (
            db.query(Message)
            .options(selectinload(Message.attachments))
            .filter(
                Message.thread_id == thread.id,
                Message.sender_id == sender.id,
                Message.client_message_id == message_key,
            )
            .first()
        )
        if existing:
            await _close_uploads(uploads, voice_upload)
            return existing, False

    clean_body = (body or "").strip()
    has_upload = any(upload and (upload.filename or "").strip() for upload in (uploads or []))
    has_voice = bool(voice_upload and (voice_upload.filename or "").strip())
    if not clean_body and not has_upload and not has_voice:
        await _close_uploads(uploads, voice_upload)
        raise HTTPException(status_code=422, detail="Write a message, attach a file, or record a voice message first.")

    # Upload validation is deliberately outside the row lock so one slow file
    # never blocks other messages.  The lock below serializes the final
    # idempotency re-check and last_message_at update.
    staged = await stage_message_attachments(
        uploads,
        voice_upload=voice_upload,
        voice_duration_ms=voice_duration_ms,
    )
    if not clean_body and not staged:
        raise HTTPException(status_code=422, detail="Write a message, attach a file, or record a voice message first.")

    locked_thread = (
        db.query(MessageThread)
        .options(lazyload("*"))
        .filter(MessageThread.id == thread.id)
        .with_for_update(of=MessageThread)
        .first()
    )
    if not locked_thread or sender.id not in (locked_thread.user_a_id, locked_thread.user_b_id):
        cleanup_staged_message_attachments(staged)
        raise HTTPException(status_code=404, detail="Conversation not found")

    if message_key:
        existing = (
            db.query(Message)
            .options(selectinload(Message.attachments))
            .filter(
                Message.thread_id == locked_thread.id,
                Message.sender_id == sender.id,
                Message.client_message_id == message_key,
            )
            .first()
        )
        if existing:
            cleanup_staged_message_attachments(staged)
            return existing, False

    saved_files: list[MessageAttachment] = []
    now = datetime.utcnow()
    try:
        message = Message(
            thread_id=locked_thread.id,
            sender_id=sender.id,
            body=clean_body,
            is_read=False,
            read_at=None,
            client_message_id=message_key,
            created_at=now,
        )
        db.add(message)
        db.flush()
        saved_files = persist_staged_message_attachments(
            db,
            thread_id=locked_thread.id,
            message_id=message.id,
            uploader_id=sender.id,
            staged=staged,
        )
        locked_thread.last_message_at = now
        db.commit()
    except IntegrityError:
        saved_names = [record.stored_name for record in saved_files]
        db.rollback()
        cleanup_staged_message_attachments(staged)
        remove_saved_message_attachment_files(saved_names)
        if message_key:
            existing = (
                db.query(Message)
                .options(selectinload(Message.attachments))
                .filter(
                    Message.thread_id == thread.id,
                    Message.sender_id == sender.id,
                    Message.client_message_id == message_key,
                )
                .first()
            )
            if existing:
                return existing, False
        raise
    except Exception:
        saved_names = [record.stored_name for record in saved_files]
        db.rollback()
        cleanup_staged_message_attachments(staged)
        remove_saved_message_attachment_files(saved_names)
        raise

    return (
        db.query(Message)
        .options(selectinload(Message.attachments))
        .filter(Message.id == message.id)
        .one(),
        True,
    )


@router.post("/messages/{thread_id}")
async def thread_send(
    thread_id: int,
    request: Request,
    body: str = Form(""),
    csrf_token: str = Form(""),
    client_message_id: str = Form(""),
    attachments: list[UploadFile] | None = File(None),
    voice: UploadFile | None = File(None),
    voice_duration_ms: str = Form(""),
    db: Session = Depends(get_db),
):
    u = require_login(request)
    if not u:
        return RedirectResponse(url="/login", status_code=303)

    thr = db.get(MessageThread, thread_id)
    if not thr or (u["id"] not in (thr.user_a_id, thr.user_b_id)):
        await _close_uploads(attachments, voice)
        return RedirectResponse(url="/messages", status_code=303)

    other_id = thr.user_b_id if thr.user_a_id == u["id"] else thr.user_a_id
    other = db.get(User, other_id)
    if is_account_limited(request) and not is_admin_user(other):
        await _close_uploads(attachments, voice)
        return RedirectResponse(url="/messages/support", status_code=303)

    require_csrf(request, csrf_token)
    sender = db.get(User, u["id"])
    if not sender:
        await _close_uploads(attachments, voice)
        raise HTTPException(status_code=401, detail="Login required")

    message, created = await _create_direct_message(
        db,
        request=request,
        thread=thr,
        sender=sender,
        body=body,
        uploads=attachments,
        voice_upload=voice,
        voice_duration_ms=voice_duration_ms,
        client_message_id=client_message_id,
    )
    if "application/json" in (request.headers.get("accept") or "").lower():
        return JSONResponse(
            {"ok": True, "created": created, "message": _serialize_message(message, viewer_id=sender.id)},
            status_code=201 if created else 200,
        )
    return RedirectResponse(url=f"/messages/{thr.id}", status_code=303)


@router.get("/messages/{thread_id}/attachments/{attachment_id}")
def message_attachment_download(
    thread_id: int,
    attachment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve a private direct-message file only to its conversation members."""
    _thread_for_member(db, request, thread_id, api=True)
    attachment = (
        db.query(MessageAttachment)
        .join(Message, Message.id == MessageAttachment.message_id)
        .filter(
            MessageAttachment.id == attachment_id,
            MessageAttachment.thread_id == thread_id,
            Message.thread_id == thread_id,
        )
        .first()
    )
    if not attachment:
        # Do not turn attachment ids into an oracle for another conversation.
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = message_attachment_path(attachment)
    safe_name = quote(attachment.original_name or "attachment", safe="")
    inline = str(attachment.content_type or "").startswith(("image/", "audio/"))
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Content-Disposition": f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{safe_name}",
    }
    return FileResponse(path, media_type=attachment.content_type, headers=headers)


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

typing_state = {}   # { thread_id: { user_id: datetime_expire } }


@router.post("/messages/{thread_id}/typing")
def set_typing(
    thread_id: int,
    request: Request,
    csrf_token: str = Form(""),
    active: str = Form("true"),
    db: Session = Depends(get_db),
):
    session_user, _thread, _other = _thread_for_member(db, request, thread_id, api=True)
    require_csrf(request, csrf_token)
    uid = session_user["id"]

    if str(active).lower() in {"0", "false", "no"}:
        if thread_id in typing_state:
            typing_state[thread_id].pop(uid, None)
        return {"ok": True}

    if thread_id not in typing_state:
        typing_state[thread_id] = {}
    typing_state[thread_id][uid] = datetime.utcnow() + timedelta(seconds=3)
    return {"ok": True}


@router.get("/messages/{thread_id}/typing_status")
def typing_status(thread_id: int, request: Request, db: Session = Depends(get_db)):
    session_user, _thread, _other = _thread_for_member(db, request, thread_id, api=True)
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
    u, thread, other = _thread_for_member(db, request, thread_id, api=True)
    try:
        last_id = max(0, int(request.query_params.get("after", 0)))
    except (TypeError, ValueError):
        last_id = 0
    receipt_after_raw = (request.query_params.get("receipts_after") or "").strip()
    receipt_after = None
    if receipt_after_raw:
        try:
            receipt_after = datetime.fromisoformat(receipt_after_raw.replace("Z", "+00:00"))
            if receipt_after.tzinfo is not None:
                receipt_after = receipt_after.replace(tzinfo=None)
        except ValueError:
            receipt_after = None

    # Capture the upper bound before querying, so a receipt that arrives during
    # this request is returned on the next harmless poll instead of being lost.
    next_receipt_cursor = datetime.utcnow()

    rows = (
        db.query(Message)
        .options(selectinload(Message.attachments))
        .filter(Message.thread_id == thread.id, Message.id > last_id)
        .order_by(Message.id.asc())
        .all()
    )

    # This endpoint only runs while the conversation page is visible.  Mark
    # inbound messages read server-side so the existing ✓ -> ✓✓ lifecycle is
    # equally real for text, images, files, and voice messages.
    unread_inbound = (
        db.query(Message)
        .filter(
            Message.thread_id == thread.id,
            Message.sender_id != u["id"],
            Message.is_read == False,
        )
        .all()
    )
    if unread_inbound:
        read_at = datetime.utcnow()
        for message in unread_inbound:
            message.is_read = True
            message.read_at = message.read_at or read_at
        db.commit()

    read_receipts = []
    if receipt_after is not None:
        read_receipts = [
            {"id": message_id, "read_at": read_at.isoformat()}
            for message_id, read_at in (
                db.query(Message.id, Message.read_at)
                .filter(
                    Message.thread_id == thread.id,
                    Message.sender_id == u["id"],
                    Message.is_read == True,
                    Message.read_at.is_not(None),
                    Message.read_at > receipt_after,
                    Message.read_at <= next_receipt_cursor,
                )
                .all()
            )
        ]

    return {
        "messages": [_serialize_message(message, viewer_id=u["id"]) for message in rows],
        "read_receipts": read_receipts,
        "receipt_cursor": next_receipt_cursor.isoformat(),
        "presence": user_presence(db, other.id),
    }
