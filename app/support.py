# app/support.py
from datetime import datetime, timezone
import os
from typing import Sequence

from fastapi import APIRouter, Request, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .models import SupportAttachment, SupportMessage, SupportMessageReceipt, SupportTicket, User

# ✅ import internal notifications function
from .notifications_api import push_notification
from .support_ai import (
    check_message_rate,
    get_or_create_csrf_token,
    require_csrf,
    validate_client_message_id,
)
from .support_attachments import (
    allowed_accept_value,
    cleanup_staged_attachments,
    max_attachment_bytes,
    persist_staged_support_attachments,
    remove_saved_attachment_files,
    serialize_support_attachment,
    stage_support_attachments,
    support_attachment_path,
)

router = APIRouter()

DEFAULT_SUPPORT_MESSAGE_MAX_CHARS = 6000


def support_message_max_chars() -> int:
    raw = os.getenv("SEVOR_SUPPORT_MESSAGE_MAX_CHARS", "").strip()
    if not raw:
        return DEFAULT_SUPPORT_MESSAGE_MAX_CHARS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SUPPORT_MESSAGE_MAX_CHARS
    return value if 500 <= value <= 20000 else DEFAULT_SUPPORT_MESSAGE_MAX_CHARS


def _timestamp_iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _is_legacy_ticket(ticket: SupportTicket | None) -> bool:
    """The focused human-ticket UI must never mutate AI chatbot conversations."""
    return bool(ticket and getattr(ticket, "channel", None) != "chatbot")


def _session_db_user(db: Session, request: Request) -> User | None:
    session_user = request.session.get("user") or {}
    user_id = session_user.get("id") if isinstance(session_user, dict) else None
    return db.get(User, user_id) if user_id else None


def _is_admin(user: User | None) -> bool:
    return bool(
        user
        and (
            str(getattr(user, "role", "")).lower() == "admin"
            or bool(getattr(user, "is_admin", False))
            or bool(getattr(user, "badge_admin", False))
        )
    )


def staff_can_view_legacy_ticket(ticket: SupportTicket, user: User | None) -> bool:
    """Restrict private attachment access to the ticket's real support queue."""
    if not _is_legacy_ticket(ticket) or not user:
        return False
    if _is_admin(user):
        return True
    queue = str(getattr(ticket, "queue", None) or "cs").strip().lower()
    if ticket.assigned_to_id == user.id:
        return True
    if queue == "cs":
        return bool(getattr(user, "is_support", False))
    if queue == "md":
        return bool(getattr(user, "is_deposit_manager", False))
    if queue == "mod":
        return bool(getattr(user, "is_mod", False))
    return False


def _receipt_ids_for_customer(db: Session, ticket: SupportTicket) -> set[int]:
    """Return user-authored messages actually viewed by a human support member."""
    rows = (
        db.query(SupportMessageReceipt.message_id)
        .join(SupportMessage, SupportMessage.id == SupportMessageReceipt.message_id)
        .filter(
            SupportMessage.ticket_id == ticket.id,
            SupportMessage.sender_role == "user",
            SupportMessageReceipt.reader_id != ticket.user_id,
        )
        .all()
    )
    return {int(row[0]) for row in rows}


def mark_legacy_ticket_messages_read(
    db: Session,
    *,
    ticket: SupportTicket,
    reader: User,
    reader_role: str,
) -> bool:
    """Persist real per-message receipts once a participant views the ticket.

    A customer reads agent/system messages; a support worker reads customer
    messages.  ``is_read`` remains updated as the legacy aggregate used by
    existing inboxes, while receipts retain the actual reader and timestamp.
    """
    if reader_role not in {"user", "agent"}:
        raise ValueError("Unsupported receipt role")
    source_roles = ("agent", "system") if reader_role == "user" else ("user",)
    messages = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.ticket_id == ticket.id,
            SupportMessage.sender_role.in_(source_roles),
        )
        .all()
    )
    if not messages:
        if reader_role == "user":
            ticket.unread_for_user = False
        else:
            ticket.unread_for_agent = False
        db.commit()
        return False

    message_ids = [message.id for message in messages]
    existing_ids = {
        row[0]
        for row in db.query(SupportMessageReceipt.message_id)
        .filter(
            SupportMessageReceipt.reader_id == reader.id,
            SupportMessageReceipt.message_id.in_(message_ids),
        )
        .all()
    }
    now = datetime.utcnow()
    changed = False
    for message in messages:
        if message.id not in existing_ids:
            db.add(
                SupportMessageReceipt(
                    message_id=message.id,
                    reader_id=reader.id,
                    read_at=now,
                )
            )
            changed = True
        if not message.is_read:
            message.is_read = True
            changed = True

    if reader_role == "user":
        if ticket.unread_for_user:
            changed = True
        ticket.unread_for_user = False
    else:
        if ticket.unread_for_agent:
            changed = True
        ticket.unread_for_agent = False
    if changed:
        db.commit()
    return changed


def serialize_legacy_support_message(
    message: SupportMessage,
    *,
    ticket: SupportTicket,
    read_by_support_ids: set[int],
) -> dict[str, object]:
    sender_role = str(message.sender_role or "user").lower()
    sender_name = "You" if sender_role == "user" else "SEVOR Support"
    if sender_role == "agent" and message.sender and message.sender.first_name:
        sender_name = message.sender.first_name
    return {
        "id": message.id,
        "sender_role": sender_role,
        "sender_name": sender_name,
        "body": message.body or "",
        "created_at": _timestamp_iso(message.created_at),
        "attachments": [
            serialize_support_attachment(attachment, ticket_id=ticket.id)
            for attachment in (message.attachments or [])
        ],
        # A single check means persisted server-side.  Double check is exposed
        # only when an actual support receipt exists.
        "read_by_support": sender_role == "user"
        and (message.id in read_by_support_ids or bool(message.is_read)),
    }


async def create_legacy_support_message(
    db: Session,
    *,
    request: Request,
    ticket: SupportTicket,
    sender: User,
    sender_role: str,
    body: str,
    uploads: Sequence[UploadFile] | None = None,
    client_message_id: str | None = None,
) -> tuple[SupportMessage, bool]:
    """Persist one idempotent text/file message and its ticket updates.

    This is intentionally shared by the customer, CS, MD, and MOD reply
    routes.  It preserves the legacy ticket lifecycle, including its existing
    reopen-on-customer-reply behavior for resolved tickets.
    """
    if not _is_legacy_ticket(ticket):
        raise HTTPException(status_code=404, detail="Support ticket not found")
    if sender_role not in {"user", "agent"}:
        raise HTTPException(status_code=422, detail="Unsupported sender role")

    message_key = validate_client_message_id(client_message_id)
    if message_key:
        existing = (
            db.query(SupportMessage)
            .filter(
                SupportMessage.ticket_id == ticket.id,
                SupportMessage.client_message_id == message_key,
            )
            .first()
        )
        if existing:
            for upload in uploads or []:
                try:
                    await upload.close()
                except Exception:
                    pass
            return existing, False

    clean_body = (body or "").strip()
    if len(clean_body) > support_message_max_chars():
        raise HTTPException(
            status_code=422,
            detail=f"Messages must be {support_message_max_chars()} characters or shorter.",
        )
    staged = await stage_support_attachments(uploads)
    if not clean_body and not staged:
        raise HTTPException(status_code=422, detail="Write a message or attach a file before sending.")

    check_message_rate(request, sender)
    now = datetime.utcnow()
    saved_files: list[SupportAttachment] = []
    try:
        message = SupportMessage(
            ticket_id=ticket.id,
            sender_id=sender.id,
            sender_role=sender_role,
            body=clean_body,
            created_at=now,
            client_message_id=message_key,
        )
        db.add(message)
        db.flush()
        saved_files = persist_staged_support_attachments(
            db,
            ticket_id=ticket.id,
            message_id=message.id,
            uploader_id=sender.id,
            staged=staged,
        )

        ticket.last_msg_at = now
        ticket.updated_at = now
        ticket.last_from = "user" if sender_role == "user" else "agent"
        if sender_role == "user":
            if ticket.status == "resolved":
                ticket.status = "open"
            ticket.unread_for_agent = True
            ticket.unread_for_user = False
        else:
            if ticket.status in (None, "new", "resolved"):
                ticket.status = "open"
            if not ticket.assigned_to_id:
                ticket.assigned_to_id = sender.id
            ticket.unread_for_user = True
            ticket.unread_for_agent = False

        db.commit()
        return message, True
    except Exception:
        db.rollback()
        cleanup_staged_attachments(staged)
        remove_saved_attachment_files(saved_files)
        raise


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
        # last message from support
        t.last_from = "agent"
        # confirm assignment + keep it open
        if not t.assigned_to_id:
            t.assigned_to_id = author_user.id
        if t.status in (None, "new", "resolved"):
            t.status = "open"
        # read by agent now
        t.unread_for_agent = False
        # mark as unread for user so they will see the reply
        t.unread_for_user = True
    else:
        # last message from the customer
        t.last_from = "user"
        # if closed, reopen it
        if t.status == "resolved":
            t.status = "open"
        # became unread for agent
        t.unread_for_agent = True

    db.commit()


def _ensure_cs_session(db: Session, request: Request):
    """
    ✅ Used as a smart "fallback":
    - If the session does not have is_support=True but the user in DB has become CS,
      update the session immediately within the same request and return the updated session_user.
    - If not logged in or not actually CS, return None.
    """
    sess = request.session.get("user") or {}
    uid = sess.get("id")
    if not uid:
        return None

    # if session already has is_support=True, return it as-is
    if bool(sess.get("is_support", False)):
        return sess

    # old session? verify with DB
    u_db = db.get(User, uid)
    if u_db and bool(getattr(u_db, "is_support", False)):
        # update session in the same request then return it
        sess["is_support"] = True
        request.session["user"] = sess
        return sess

    # not actually CS
    return None


# ✅ function to notify all CS agents when a new ticket is opened
def _notify_support_agents_on_new_ticket(db: Session, ticket: SupportTicket):
    agents = (
        db.query(User)
        .filter(User.is_support == True, User.status == "approved")
        .all()
    )
    # you can keep the direct ticket link or make it /cs/inbox per team preference
    url = f"/cs/ticket/{ticket.id}"
    title = "🎫 New support ticket"
    body = f"#{ticket.id} — {ticket.subject or ''}".strip()

    for ag in agents:
        try:
            push_notification(
                db,
                ag.id,
                title,
                body,
                url,
                "support",  # notification kind
            )
        except Exception:
            # do not block ticket creation if one notification fails
            pass


# ========== Customer UI ==========

@router.get("/support/new", response_class=HTMLResponse)
def support_new(request: Request):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    return request.app.templates.TemplateResponse(
        request=request,
        name="support_new.html",
        context={"request": request, "session_user": u, "title": "Contact Support"},
    )


@router.post("/support/new")
def support_new_post(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    # Starlette stores the last form in request._form — provide a safe fallback if unavailable
    form = getattr(request, "_form", None)
    if form is None:
        import anyio

        async def _read_form():
            return await request.form()

        form = anyio.from_thread.run(_read_form)

    subject = form.get("subject", "").strip() if form else ""
    body = form.get("body", "").strip() if form else ""

    if not subject:
        subject = "No subject"

    # create ticket + first message
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
        body=body or "(no text)",
        created_at=datetime.utcnow(),
    )
    db.add(m)
    db.commit()

    # ✅ after successful creation: notify CS agents
    _notify_support_agents_on_new_ticket(db, t)

    return RedirectResponse("/support/my", status_code=303)


@router.get("/support/my", response_class=HTMLResponse)
def support_my(request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    # ✅ نعرض فقط تذاكر السيبور القديم
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == u["id"])
        .filter((SupportTicket.channel == None) | (SupportTicket.channel != "chatbot"))
        .order_by(SupportTicket.updated_at.desc())
        .all()
    )

    return request.app.templates.TemplateResponse(
        request=request,
        name="support_my.html",
        context={
            "request": request,
            "session_user": u,
            "tickets": tickets,
            "title": "My Tickets",
        },
    )

@router.get("/support/ticket/{tid}", response_class=HTMLResponse)
def support_ticket_view(tid: int, request: Request, db: Session = Depends(get_db)):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    t = (
        db.query(SupportTicket)
        .options(
            selectinload(SupportTicket.messages).selectinload(SupportMessage.attachments),
            selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
        )
        .filter(SupportTicket.id == tid)
        .first()
    )
    if not t or t.user_id != u["id"]:
        return RedirectResponse("/support/my", status_code=303)

    # ✅ أهم سطر: إذا كانت التذكرة Chatbot → حوّلها لصفحة الشاتبوت
    if t.channel == "chatbot":
        return RedirectResponse(f"/chatbot/ticket/{t.id}", status_code=303)

    # ---------------------------------------
    # سيبور قديم فقط (legacy)
    # ---------------------------------------
    db_user = _session_db_user(db, request)
    if not db_user:
        return RedirectResponse("/login", status_code=303)
    # Loading this ticket is a real view by its owner.  Persist read receipts
    # for messages already rendered; polling does the same for later replies.
    mark_legacy_ticket_messages_read(db, ticket=t, reader=db_user, reader_role="user")
    read_by_support_ids = _receipt_ids_for_customer(db, t)

    return request.app.templates.TemplateResponse(
        request=request,
        name="support_ticket.html",
        context={
            "request": request,
            "session_user": u,
            "ticket": t,
            "msgs": t.messages,
            "title": f"Ticket #{t.id}",
            "csrf_token": get_or_create_csrf_token(request),
            "attachment_accept": allowed_accept_value(),
            "max_attachment_bytes": max_attachment_bytes(),
            "max_message_chars": support_message_max_chars(),
            "read_by_support_ids": read_by_support_ids,
            "message_timestamps": {message.id: _timestamp_iso(message.created_at) for message in (t.messages or [])},
            "ticket_timestamps": {
                "created": _timestamp_iso(t.created_at),
                "updated": _timestamp_iso(t.updated_at),
                "last_activity": _timestamp_iso(t.last_msg_at or t.updated_at or t.created_at),
            },
            # This focused human-support view intentionally suppresses base
            # marketplace chrome, PayPal prompts, and bottom navigation.
            "immersive": True,
            "no_ui": True,
        },
    )


@router.get("/support/ticket/{tid}/updates")
def support_ticket_updates(
    tid: int,
    request: Request,
    after_id: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Poll only new, authorized legacy-ticket messages and receipt changes."""
    u = _require_login(request)
    if not u:
        raise HTTPException(status_code=401, detail="Login required")
    ticket = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not _is_legacy_ticket(ticket) or ticket.user_id != u["id"]:
        raise HTTPException(status_code=404, detail="Support ticket not found")

    messages = (
        db.query(SupportMessage)
        .options(selectinload(SupportMessage.attachments), selectinload(SupportMessage.sender))
        .filter(SupportMessage.ticket_id == ticket.id, SupportMessage.id > after_id)
        .order_by(SupportMessage.id.asc())
        .all()
    )
    read_by_support_ids = _receipt_ids_for_customer(db, ticket)
    return JSONResponse(
        {
            "ticket": {
                "id": ticket.id,
                "status": ticket.status,
                "updated_at": _timestamp_iso(ticket.updated_at),
                "last_activity_at": _timestamp_iso(ticket.last_msg_at or ticket.updated_at or ticket.created_at),
                "assigned_agent": ticket.assigned_to.first_name if ticket.assigned_to and ticket.assigned_to.first_name else None,
            },
            "messages": [
                serialize_legacy_support_message(
                    message,
                    ticket=ticket,
                    read_by_support_ids=read_by_support_ids,
                )
                for message in messages
            ],
            "read_by_support_message_ids": sorted(read_by_support_ids),
        }
    )


@router.post("/support/ticket/{tid}/read")
def support_ticket_mark_read(
    tid: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create receipts only after the customer's rendered ticket is visible."""
    u = _require_login(request)
    if not u:
        raise HTTPException(status_code=401, detail="Login required")
    require_csrf(request, csrf_token)
    ticket = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    if not _is_legacy_ticket(ticket) or ticket.user_id != u["id"]:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    reader = _session_db_user(db, request)
    if not reader:
        raise HTTPException(status_code=401, detail="Login required")
    mark_legacy_ticket_messages_read(db, ticket=ticket, reader=reader, reader_role="user")
    return {"ok": True}


@router.get("/support/ticket/{tid}/attachments/{attachment_id}")
def support_ticket_attachment_download(
    tid: int,
    attachment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve a private support file only after current ticket authorization."""
    session_user = _require_login(request)
    if not session_user:
        raise HTTPException(status_code=401, detail="Login required")
    attachment = (
        db.query(SupportAttachment)
        .filter(SupportAttachment.id == attachment_id, SupportAttachment.ticket_id == tid)
        .first()
    )
    ticket = db.query(SupportTicket).filter(SupportTicket.id == tid).first()
    actor = _session_db_user(db, request)
    if (
        not attachment
        or not _is_legacy_ticket(ticket)
        or not actor
        or not (ticket.user_id == actor.id or staff_can_view_legacy_ticket(ticket, actor))
    ):
        # Use the same response for absent and unauthorized files to avoid an
        # attachment-ID oracle.
        raise HTTPException(status_code=404, detail="Attachment not found")

    path = support_attachment_path(attachment)
    from urllib.parse import quote

    safe_name = quote(attachment.original_name or "attachment", safe="")
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Content-Disposition": f"inline; filename*=UTF-8''{safe_name}",
    }
    return FileResponse(path, media_type=attachment.content_type, headers=headers)


@router.post("/support/ticket/{tid}/reply")
async def support_ticket_reply(
    tid: int,
    request: Request,
    body: str = Form(""),
    csrf_token: str = Form(""),
    client_message_id: str = Form(""),
    attachments: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    u = _require_login(request)
    if not u:
        return RedirectResponse("/login", status_code=303)

    t = db.get(SupportTicket, tid)
    if not t or t.user_id != u["id"]:
        return RedirectResponse("/support/my", status_code=303)
    # Chatbot conversations use their own authenticated message/state
    # boundary.  This legacy form must never reopen or mutate one.
    if t.channel == "chatbot":
        return RedirectResponse(f"/chatbot/ticket/{t.id}", status_code=303)
    require_csrf(request, csrf_token)
    sender = _session_db_user(db, request)
    if not sender:
        raise HTTPException(status_code=401, detail="Login required")

    m, created = await create_legacy_support_message(
        db,
        request=request,
        ticket=t,
        sender=sender,
        sender_role="user",
        body=body,
        uploads=attachments,
        client_message_id=client_message_id,
    )

    # notify the assigned agent if any, otherwise all approved CS staff
    if created and t.assigned_to_id:
        push_notification(
            db,
            t.assigned_to_id,
            "💬 New customer reply",
            f"#{t.id} — {t.subject or ''}",
            url=f"/cs/ticket/{t.id}",
            kind="support",
        )
    elif created:
        agents = db.query(User).filter(User.is_support==True, User.status=="approved").all()
        for ag in agents:
            push_notification(
                db,
                ag.id,
                "💬 New customer reply",
                f"#{t.id} — {t.subject or ''}",
                url=f"/cs/ticket/{t.id}",
                kind="support",
            )

    if "application/json" in (request.headers.get("accept") or "").lower():
        refreshed = (
            db.query(SupportMessage)
            .options(selectinload(SupportMessage.attachments), selectinload(SupportMessage.sender))
            .filter(SupportMessage.id == m.id)
            .first()
        )
        return JSONResponse(
            {
                "ok": True,
                "created": created,
                "message": serialize_legacy_support_message(
                    refreshed or m,
                    ticket=t,
                    read_by_support_ids=_receipt_ids_for_customer(db, t),
                ),
                "ticket": {"id": t.id, "status": t.status},
            },
            status_code=201 if created else 200,
        )
    return RedirectResponse(f"/support/ticket/{t.id}", status_code=303)
