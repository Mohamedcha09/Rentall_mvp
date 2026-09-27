"""The existing /chatbot route, evolved into persistent Sevor AI Support."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .auth import get_current_user
from .database import get_db
from .models import SupportMessage, SupportTicket, User
from .notifications_api import push_notification
from .support_ai import (
    AGENT_ACTIVE,
    AI_ACTIVE,
    MAX_AI_ATTEMPTS,
    RESOLVED,
    WAITING_FOR_AGENT,
    append_message,
    authorize_ticket_access,
    check_message_rate,
    copy_for,
    create_ai_answer,
    create_ai_conversation,
    detect_language,
    find_user_conversation,
    get_or_create_csrf_token,
    get_or_create_user_conversation,
    handoff_to_human_atomically,
    is_handoff_request,
    lock_agent_ticket_for_mutation,
    notify_waiting_agents,
    provider_available,
    read_metadata,
    resolve_ai_conversation_atomically,
    require_chatbot_ticket,
    require_csrf,
    serialize_message,
    serialize_ticket,
    set_ticket_state,
    ticket_state,
    update_ticket_summary,
    validate_client_message_id,
    validate_message,
    write_metadata,
)
from .utils import display_currency


router = APIRouter(tags=["chatbot"])
templates = Jinja2Templates(directory="app/templates")
_TREE_PATH = Path(__file__).resolve().parent / "chatbot" / "tree.json"


class ChatMessagePayload(BaseModel):
    body: str
    conversation_id: Optional[int] = None
    client_message_id: Optional[str] = None
    csrf_token: Optional[str] = None


class FeedbackPayload(BaseModel):
    choice: str
    message_id: Optional[int] = None
    csrf_token: Optional[str] = None


class HandoffPayload(BaseModel):
    csrf_token: Optional[str] = None
    reason: Optional[str] = None


class NewConversationPayload(BaseModel):
    csrf_token: Optional[str] = None


def _load_tree() -> dict:
    with _TREE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _ticket_messages(db: Session, ticket: SupportTicket, after_id: int = 0) -> list[SupportMessage]:
    query = (
        db.query(SupportMessage)
        .options(joinedload(SupportMessage.sender))
        .filter(SupportMessage.ticket_id == ticket.id)
        .order_by(SupportMessage.id.desc())
    )
    if after_id > 0:
        rows = query.filter(SupportMessage.id > after_id).limit(100).all()
        return list(reversed(rows))
    # A refresh restores a bounded history rather than loading thousands of rows.
    return list(reversed(query.limit(100).all()))


def _conversation_payload(db: Session, ticket: Optional[SupportTicket], after_id: int = 0) -> dict:
    if not ticket:
        return {"ok": True, "conversation": None, "messages": [], "ai_available": provider_available()}
    return {
        "ok": True,
        "conversation": serialize_ticket(ticket),
        "messages": [serialize_message(message) for message in _ticket_messages(db, ticket, after_id)],
        "ai_available": provider_available(),
    }


def _get_ticket(db: Session, ticket_id: int) -> SupportTicket:
    ticket = (
        db.query(SupportTicket)
        .options(joinedload(SupportTicket.assigned_to))
        .filter(SupportTicket.id == ticket_id)
        .first()
    )
    return require_chatbot_ticket(ticket)


def _find_idempotent_message(db: Session, ticket: SupportTicket, client_message_id: Optional[str]) -> Optional[SupportMessage]:
    if not client_message_id:
        return None
    return (
        db.query(SupportMessage)
        .options(joinedload(SupportMessage.sender))
        .filter(
            SupportMessage.ticket_id == ticket.id,
            SupportMessage.client_message_id == client_message_id,
            SupportMessage.sender_role == "user",
        )
        .first()
    )


def _persist_user_message(db: Session, ticket: SupportTicket, user: User, body: str, client_message_id: Optional[str]) -> SupportMessage:
    message = append_message(db, ticket, user, "user", body, client_message_id=client_message_id)
    now = datetime.utcnow()
    ticket.last_from = "user"
    ticket.last_msg_at = now
    ticket.updated_at = now
    ticket.unread_for_agent = ticket_state(ticket) in {WAITING_FOR_AGENT, AGENT_ACTIVE}
    ticket.unread_for_user = False
    db.flush()
    return message


def _commit_user_message_or_duplicate(
    db: Session,
    ticket: SupportTicket,
    client_message_id: Optional[str],
) -> Optional[dict]:
    """A database unique index closes the double-click/retry race as well."""
    try:
        db.commit()
        return None
    except IntegrityError:
        db.rollback()
        refreshed = _get_ticket(db, ticket.id)
        duplicate = _find_idempotent_message(db, refreshed, client_message_id)
        if duplicate:
            return _conversation_payload(db, refreshed)
        raise


def _provider_answer_for_message(db: Session, ticket: SupportTicket, user: User, user_message: SupportMessage, body: str) -> Optional[SupportMessage]:
    """Generate only while the conversation is still AI-owned and in order."""
    answer, metadata = create_ai_answer(db, user, ticket, body)
    # Take a short database lock *after* the external call.  An agent claim or
    # later user message that committed first wins; the assistant response is
    # then discarded instead of appearing after a human has joined.
    locked_ticket = (
        db.query(SupportTicket)
        .filter(SupportTicket.id == ticket.id, SupportTicket.channel == "chatbot")
        .with_for_update()
        .first()
    )
    if not locked_ticket or ticket_state(locked_ticket) != AI_ACTIVE:
        return None
    newest_id = (
        db.query(SupportMessage.id)
        .filter(SupportMessage.ticket_id == locked_ticket.id)
        .order_by(SupportMessage.id.desc())
        .limit(1)
        .scalar()
    )
    if newest_id != user_message.id:
        # A later user message or a human handoff arrived while the model ran.
        return None
    assistant = append_message(db, locked_ticket, user, "assistant", answer, metadata=metadata)
    now = datetime.utcnow()
    locked_ticket.last_from = "assistant"
    locked_ticket.last_msg_at = now
    locked_ticket.updated_at = now
    locked_ticket.unread_for_user = True
    locked_ticket.unread_for_agent = False
    update_ticket_summary(db, locked_ticket)
    return assistant


def _assistant_attempt_count(db: Session, ticket: SupportTicket) -> int:
    return (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == ticket.id, SupportMessage.sender_role == "assistant")
        .count()
    )


def _handoff_after_user_message(
    db: Session,
    ticket: SupportTicket,
    user: User,
    body: str,
    reason: str,
) -> tuple[SupportTicket, bool]:
    current, event = handoff_to_human_atomically(
        db,
        ticket,
        user,
        language=detect_language(body),
        reason=reason,
    )
    return current, event is not None


def _queue_agents(db: Session, queue: str) -> list[User]:
    if queue == "cs_chatbot":
        return db.query(User).filter(User.is_support == True).all()
    if queue == "md_chatbot":
        return db.query(User).filter((User.is_deposit_manager == True) | (User.badge_admin == True)).all()
    if queue == "mod_chatbot":
        return db.query(User).filter(User.is_mod == True).all()
    return []


def _notify_queue(db: Session, ticket: SupportTicket, queue: str, title: str) -> None:
    route_prefix = {"cs_chatbot": "cs", "md_chatbot": "md", "mod_chatbot": "mod"}.get(queue, "cs")
    for agent in _queue_agents(db, queue):
        try:
            push_notification(
                db,
                agent.id,
                title,
                f"Support conversation #{ticket.id} is waiting in your queue.",
                url=f"/{route_prefix}/chatbot/ticket/{ticket.id}",
                kind="support",
            )
        except Exception:
            # The queue row is already persisted; email/notification failure is non-fatal.
            pass


@router.get("/chatbot/tree")
def get_chatbot_tree():
    """Backward-compatible FAQ data. The browser renders it as text only."""
    return JSONResponse(content=_load_tree(), headers={"Cache-Control": "no-store"})


@router.get("/chatbot")
def chatbot_page(
    request: Request,
    conversation: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    active_ticket = find_user_conversation(db, user, conversation) if user else None
    return templates.TemplateResponse(
        request=request,
        name="chatbot.html",
        context={
            "request": request,
            "user": user,
            "session_user": user,
            "active_ticket": active_ticket,
            "csrf_token": get_or_create_csrf_token(request),
            "ai_available": provider_available(),
            "display_currency": display_currency,
        },
    )


@router.get("/api/chatbot/conversation")
def chatbot_conversation(
    conversation_id: Optional[int] = Query(None, ge=1),
    after_id: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return _conversation_payload(db, None)
    ticket = find_user_conversation(db, user, conversation_id)
    return _conversation_payload(db, ticket, after_id)


@router.post("/api/chatbot/conversation/new")
def chatbot_new_conversation(
    payload: NewConversationPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    require_csrf(request, payload.csrf_token)
    check_message_rate(request, user)
    existing = find_user_conversation(db, user)
    if existing:
        return _conversation_payload(db, existing)
    ticket = create_ai_conversation(db, user)
    db.commit()
    db.refresh(ticket)
    return _conversation_payload(db, ticket)


@router.post("/api/chatbot/conversation/message")
def chatbot_send_ai_message(
    payload: ChatMessagePayload,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    require_csrf(request, payload.csrf_token)
    check_message_rate(request, user)
    body = validate_message(payload.body)
    client_message_id = validate_client_message_id(payload.client_message_id)
    ticket = get_or_create_user_conversation(db, user, payload.conversation_id)
    state = ticket_state(ticket)
    if state == RESOLVED:
        raise HTTPException(status_code=409, detail="Start a new conversation for a new issue")

    duplicate = _find_idempotent_message(db, ticket, client_message_id)
    if duplicate:
        return _conversation_payload(db, ticket)

    user_message = _persist_user_message(db, ticket, user, body, client_message_id)
    if state in {WAITING_FOR_AGENT, AGENT_ACTIVE}:
        duplicate_payload = _commit_user_message_or_duplicate(db, ticket, client_message_id)
        if duplicate_payload:
            return duplicate_payload
        db.refresh(ticket)
        return _conversation_payload(db, ticket)

    if is_handoff_request(body):
        ticket, handoff_created = _handoff_after_user_message(db, ticket, user, body, "user_requested_human")
        duplicate_payload = _commit_user_message_or_duplicate(db, ticket, client_message_id)
        if duplicate_payload:
            return duplicate_payload
        db.refresh(ticket)
        if handoff_created:
            notify_waiting_agents(db, ticket)
        return _conversation_payload(db, ticket)

    if _assistant_attempt_count(db, ticket) >= MAX_AI_ATTEMPTS:
        ticket, handoff_created = _handoff_after_user_message(db, ticket, user, body, "ai_attempt_limit")
        duplicate_payload = _commit_user_message_or_duplicate(db, ticket, client_message_id)
        if duplicate_payload:
            return duplicate_payload
        db.refresh(ticket)
        if handoff_created:
            notify_waiting_agents(db, ticket)
        return _conversation_payload(db, ticket)

    # Persist first: a refresh/reconnect still has the user's message if an
    # external provider times out or becomes unavailable.
    duplicate_payload = _commit_user_message_or_duplicate(db, ticket, client_message_id)
    if duplicate_payload:
        return duplicate_payload
    db.refresh(ticket)
    _provider_answer_for_message(db, ticket, user, user_message, body)
    db.commit()
    db.refresh(ticket)
    return _conversation_payload(db, ticket)


@router.post("/api/chatbot/conversation/{ticket_id}/feedback")
def chatbot_feedback(
    ticket_id: int,
    payload: FeedbackPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    require_csrf(request, payload.csrf_token)
    check_message_rate(request, user)
    ticket = _get_ticket(db, ticket_id)
    if authorize_ticket_access(ticket, user) != "user":
        raise HTTPException(status_code=403, detail="Not allowed")
    if ticket_state(ticket) != AI_ACTIVE:
        raise HTTPException(status_code=409, detail="This AI feedback is no longer active")
    choice = (payload.choice or "").strip().lower()
    if choice not in {"yes", "no"}:
        raise HTTPException(status_code=422, detail="Feedback must be yes or no")
    message = None
    if payload.message_id:
        message = (
            db.query(SupportMessage)
            .filter(
                SupportMessage.id == payload.message_id,
                SupportMessage.ticket_id == ticket.id,
                SupportMessage.sender_role == "assistant",
            )
            .first()
        )
    if not message:
        message = (
            db.query(SupportMessage)
            .filter(SupportMessage.ticket_id == ticket.id, SupportMessage.sender_role == "assistant")
            .order_by(SupportMessage.id.desc())
            .first()
        )
    if not message:
        raise HTTPException(status_code=409, detail="No AI solution is awaiting feedback")
    metadata = read_metadata(message)
    if metadata.get("feedback"):
        return _conversation_payload(db, ticket)
    language = detect_language(message.body or "")
    if choice == "yes":
        ticket = resolve_ai_conversation_atomically(db, ticket, user, language=language)
        metadata["feedback"] = "helpful"
        metadata["feedback_prompt"] = False
        write_metadata(message, metadata)
        update_ticket_summary(db, ticket)
        db.commit()
        db.refresh(ticket)
        return _conversation_payload(db, ticket)

    ticket, handoff_created = _handoff_after_user_message(db, ticket, user, message.body or "", "ai_solution_not_helpful")
    if not handoff_created:
        raise HTTPException(status_code=409, detail="This AI feedback is no longer active")
    metadata["feedback"] = "not_helpful"
    metadata["feedback_prompt"] = False
    write_metadata(message, metadata)
    update_ticket_summary(db, ticket)
    db.commit()
    db.refresh(ticket)
    if handoff_created:
        notify_waiting_agents(db, ticket)
    return _conversation_payload(db, ticket)


@router.post("/api/chatbot/conversation/{ticket_id}/handoff")
def chatbot_handoff(
    ticket_id: int,
    payload: HandoffPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    require_csrf(request, payload.csrf_token)
    check_message_rate(request, user)
    ticket = _get_ticket(db, ticket_id)
    if authorize_ticket_access(ticket, user) != "user":
        raise HTTPException(status_code=403, detail="Not allowed")
    current_state = ticket_state(ticket)
    if current_state == AGENT_ACTIVE:
        return _conversation_payload(db, ticket)
    if current_state == WAITING_FOR_AGENT:
        return _conversation_payload(db, ticket)
    if current_state == RESOLVED:
        raise HTTPException(status_code=409, detail="Start a new conversation for a new issue")
    ticket, handoff_created = _handoff_after_user_message(db, ticket, user, payload.reason or "", "user_requested_human")
    db.commit()
    db.refresh(ticket)
    if handoff_created:
        notify_waiting_agents(db, ticket)
    return _conversation_payload(db, ticket)


# Legacy API routes remain reachable for existing links, but now share the
# same ownership/role boundary. The redesigned /chatbot uses the endpoints above.
@router.get("/api/chatbot/agent_status/{ticket_id}")
def chatbot_agent_status(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ticket = _get_ticket(db, ticket_id)
    authorize_ticket_access(ticket, user)
    payload = serialize_ticket(ticket)
    return {"ticket_id": ticket.id, "assigned": payload["assigned"], "agent_name": payload["agent_name"], "state": payload["state"]}


@router.get("/api/chatbot/messages/{ticket_id}")
def chatbot_get_messages(
    ticket_id: int,
    after_id: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    ticket = _get_ticket(db, ticket_id)
    authorize_ticket_access(ticket, user)
    return _conversation_payload(db, ticket, after_id)


@router.post("/api/chatbot/messages/{ticket_id}")
def chatbot_send_legacy_message(
    ticket_id: int,
    request: Request,
    body: str = Form(...),
    csrf_token: Optional[str] = Form(None),
    client_message_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    require_csrf(request, csrf_token)
    check_message_rate(request, user)
    ticket = _get_ticket(db, ticket_id)
    role = authorize_ticket_access(ticket, user)
    cleaned = validate_message(body)
    if role == "user":
        payload = ChatMessagePayload(body=cleaned, conversation_id=ticket.id, client_message_id=client_message_id, csrf_token=csrf_token)
        return chatbot_send_ai_message(payload, request, db, user)
    # The browser may have loaded this legacy endpoint before a transfer or
    # close.  Re-fetch under a lock and authorize the current assignee before
    # appending, so a stale agent request cannot revive another queue's or a
    # closed conversation.
    ticket, _ = lock_agent_ticket_for_mutation(
        db,
        ticket.id,
        user,
        claim_if_waiting=False,
    )
    message = append_message(db, ticket, user, "agent", cleaned)
    now = datetime.utcnow()
    ticket.last_from = "agent"
    ticket.last_msg_at = now
    ticket.updated_at = now
    ticket.unread_for_user = True
    ticket.unread_for_agent = False
    db.commit()
    return {"ok": True, "message": serialize_message(message)}


@router.post("/chatbot/support")
def chatbot_open_legacy_ticket(
    request: Request,
    question: str = Form(...),
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Compatibility for the former FAQ No button; client answers are never trusted."""
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    require_csrf(request, csrf_token)
    check_message_rate(request, user)
    question = validate_message(question)
    ticket = create_ai_conversation(db, user)
    _persist_user_message(db, ticket, user, question, None)
    ticket, handoff_created = _handoff_after_user_message(db, ticket, user, question, "legacy_faq_not_helpful")
    db.commit()
    db.refresh(ticket)
    if handoff_created:
        notify_waiting_agents(db, ticket)
    return {"ok": True, "ticket_id": ticket.id}


@router.post("/chatbot/ticket/{ticket_id}/transfer")
def chatbot_transfer_ticket(
    ticket_id: int,
    request: Request,
    new_queue: str = Form(...),
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    require_csrf(request, csrf_token)
    ticket = _get_ticket(db, ticket_id)
    if authorize_ticket_access(ticket, user) != "agent":
        raise HTTPException(status_code=403, detail="Not allowed")
    # A ticket may have been transferred or closed after the caller opened its
    # agent view.  Lock and re-check the live row before changing queue/state.
    ticket, _ = lock_agent_ticket_for_mutation(
        db,
        ticket.id,
        user,
        claim_if_waiting=False,
    )
    transfer_map = {
        "cs_chatbot": "Your conversation has been transferred to Sevor Customer Support.",
        "md_chatbot": "Your conversation has been transferred to Sevor Management Desk.",
        "mod_chatbot": "Your conversation has been transferred to Sevor Moderation Team.",
    }
    if new_queue not in transfer_map:
        raise HTTPException(status_code=422, detail="Invalid queue")
    if new_queue == ticket.queue:
        # A no-op transfer must not clear the current assignee.  Keeping the
        # live state also prevents a stale reply form from turning a harmless
        # repeat click into a fresh queue claim.
        return {"ok": True, "queue": new_queue, "status": "already_in_queue"}
    now = datetime.utcnow()
    append_message(db, ticket, user, "system", transfer_map[new_queue], metadata={"event": "transferred", "queue": new_queue})
    ticket.queue = new_queue
    ticket.assigned_to_id = None
    ticket.status = "new"
    set_ticket_state(ticket, WAITING_FOR_AGENT)
    ticket.last_from = "user"
    ticket.last_msg_at = now
    ticket.updated_at = now
    ticket.unread_for_user = True
    ticket.unread_for_agent = True
    update_ticket_summary(db, ticket)
    db.commit()
    db.refresh(ticket)
    _notify_queue(db, ticket, new_queue, "Sevor support transfer")
    return {"ok": True, "queue": new_queue}


@router.post("/chatbot/ticket/{ticket_id}/close")
def chatbot_close_ticket(
    ticket_id: int,
    request: Request,
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    require_csrf(request, csrf_token)
    ticket = _get_ticket(db, ticket_id)
    if authorize_ticket_access(ticket, user) != "agent":
        raise HTTPException(status_code=403, detail="Not allowed")
    # See transfer above: this is a state transition, not just a UI action,
    # so it must use the current locked assignment rather than a stale read.
    try:
        ticket, _ = lock_agent_ticket_for_mutation(
            db,
            ticket.id,
            user,
            claim_if_waiting=False,
        )
    except HTTPException as exc:
        # Closing is intentionally idempotent for the agent that submitted it;
        # a concurrent close must not turn into an error or revive the ticket.
        if exc.status_code == 409 and exc.detail == "Conversation is closed":
            return {"ok": True, "status": "already_closed"}
        raise
    now = datetime.utcnow()
    closer_name = (user.full_name or user.first_name or "Sevor Support").strip()
    append_message(db, ticket, user, "system", f"This conversation has been closed by {closer_name}.", metadata={"event": "closed"})
    ticket.status = "closed"
    ticket.closed_by = closer_name
    ticket.closed_at = now
    ticket.resolved_at = now
    set_ticket_state(ticket, RESOLVED)
    ticket.last_from = "system"
    ticket.last_msg_at = now
    ticket.updated_at = now
    ticket.unread_for_user = True
    ticket.unread_for_agent = False
    update_ticket_summary(db, ticket)
    db.commit()
    return {"ok": True, "status": "closed", "closed_by": closer_name}


@router.get("/chatbot/ticket/{ticket_id}")
@router.get("/support/chatbot/ticket/{ticket_id}")
def chatbot_ticket_client_redirect(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    ticket = _get_ticket(db, ticket_id)
    if authorize_ticket_access(ticket, user) != "user":
        raise HTTPException(status_code=403, detail="Not allowed")
    return RedirectResponse(f"/chatbot?conversation={ticket.id}", status_code=303)
