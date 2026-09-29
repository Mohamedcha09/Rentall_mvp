"""Routes for Sevor Finder, kept separate from Support AI and direct messages."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
import json
import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import get_current_user
from .database import get_db
from .finder_service import (
    MAX_FINDER_MESSAGE_CHARS,
    SearchSpec,
    apply_user_turn,
    comparison_for_seen_listings,
    enrich_spec_with_provider,
    finder_copy,
    finder_provider_mode,
    get_listing_details,
    looks_like_support_request,
    make_assistant_search_message,
    parse_compare_positions,
    public_listings_query,
    search_rentable_listings,
    spec_summary,
    support_request_response,
)
from .models import FinderConversation, FinderMessage, FinderSearchState, Item, User
from .support_ai import get_or_create_csrf_token, require_csrf, validate_client_message_id
from .utils import display_currency


router = APIRouter(tags=["finder"])


class FinderMessagePayload(BaseModel):
    body: str
    conversation_id: Optional[int] = None
    client_message_id: Optional[str] = None
    csrf_token: Optional[str] = None
    search_revision: Optional[int] = None


class FinderNewConversationPayload(BaseModel):
    csrf_token: Optional[str] = None


class _FinderRateLimiter:
    """Finder gets its own bounded process-local bucket from Support AI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, user_id: int, *, limit: int = 15, window_seconds: int = 60) -> None:
        now = time.monotonic()
        key = f"finder:user:{int(user_id)}"
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= now - window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail="Please wait a moment before sending another Finder search.",
                    headers={"Retry-After": str(max(1, int(window_seconds - (now - bucket[0]))))},
                )
            bucket.append(now)


_RATE_LIMITER = _FinderRateLimiter()


def _require_user(user: Optional[User]) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def _owned_conversation(db: Session, user: User, conversation_id: int) -> FinderConversation:
    conversation = (
        db.query(FinderConversation)
        .filter(FinderConversation.id == int(conversation_id), FinderConversation.user_id == user.id)
        .first()
    )
    # Do not reveal whether a different user's Finder conversation exists.
    if not conversation:
        raise HTTPException(status_code=404, detail="Finder conversation not found")
    return conversation


def _create_conversation(db: Session, user: User, request: Request) -> FinderConversation:
    language = str((request.headers.get("accept-language") or "en").split(",", 1)[0]).lower()[:8]
    if language.startswith("ar"):
        language = "ar"
    elif language.startswith("fr"):
        language = "fr"
    else:
        language = "en"
    conversation = FinderConversation(user_id=user.id, language=language, status="active", active_revision=0)
    db.add(conversation)
    db.flush()
    state = FinderSearchState(conversation_id=conversation.id, revision=0, spec_json=json.dumps(SearchSpec(language=language).to_dict(), ensure_ascii=False))
    db.add(state)
    db.flush()
    return conversation


def _state_for(db: Session, conversation: FinderConversation) -> FinderSearchState:
    state = conversation.search_state or db.query(FinderSearchState).filter(FinderSearchState.conversation_id == conversation.id).one_or_none()
    if state:
        return state
    state = FinderSearchState(conversation_id=conversation.id, revision=conversation.active_revision or 0, spec_json=json.dumps(SearchSpec(language=conversation.language).to_dict(), ensure_ascii=False))
    db.add(state)
    db.flush()
    return state


def _spec_for(state: FinderSearchState, language: str) -> SearchSpec:
    try:
        raw = json.loads(state.spec_json or "{}")
    except (TypeError, ValueError):
        raw = {}
    spec = SearchSpec.from_dict(raw)
    if not spec.language:
        spec.language = language or "en"
    return spec


def _seen_ids(state: FinderSearchState) -> list[int]:
    try:
        values = json.loads(state.last_result_ids_json or "[]")
    except (TypeError, ValueError):
        values = []
    output: list[int] = []
    if isinstance(values, list):
        for raw in values:
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value > 0 and value not in output:
                output.append(value)
    return output[:100]


def _metadata(value: Optional[str]) -> dict:
    try:
        decoded = json.loads(value or "{}")
    except (TypeError, ValueError):
        decoded = {}
    return decoded if isinstance(decoded, dict) else {}


def _serialize_message(db: Session, message: FinderMessage) -> dict:
    metadata = _metadata(message.metadata_json)
    payload = {
        "id": message.id,
        "sender_role": message.sender_role,
        "body": message.body,
        "client_message_id": message.client_message_id,
        "created_at": message.created_at.isoformat() + "Z" if message.created_at else None,
    }
    if message.sender_role != "assistant":
        return payload
    payload["search_summary"] = metadata.get("search_summary")
    payload["has_more"] = bool(metadata.get("has_more"))
    payload["next_offset"] = metadata.get("next_offset")
    payload["support_url"] = metadata.get("support_url")
    raw_cards = metadata.get("result_cards")
    if isinstance(raw_cards, list):
        # Old result metadata is not a live price/status source. Rehydrate every
        # visible id from current public Items and keep only display evidence
        # from the old matching decision.
        old_by_id = {int(card.get("id")): card for card in raw_cards if isinstance(card, dict) and str(card.get("id", "")).isdigit()}
        spec = SearchSpec.from_dict(metadata.get("spec"))
        cards = []
        for fresh in get_listing_details(db, old_by_id.keys(), spec=spec):
            if fresh.get("unavailable"):
                continue
            cards.append(fresh)
        payload["result_cards"] = cards
    raw_near = metadata.get("near_cards")
    if isinstance(raw_near, list):
        near_by_id = {int(card.get("id")): card for card in raw_near if isinstance(card, dict) and str(card.get("id", "")).isdigit()}
        spec = SearchSpec.from_dict(metadata.get("spec"))
        payload["near_cards"] = [
            card for card in get_listing_details(db, near_by_id.keys(), spec=spec, include_near=True)
            if not card.get("unavailable")
        ]
    return payload


def _conversation_payload(db: Session, user: User, conversation: Optional[FinderConversation], *, after_id: int = 0) -> dict:
    if not conversation:
        return {
            "ok": True,
            "conversation": None,
            "messages": [],
            "provider_mode": finder_provider_mode(),
        }
    query = db.query(FinderMessage).filter(FinderMessage.conversation_id == conversation.id)
    if after_id > 0:
        messages = query.filter(FinderMessage.id > after_id).order_by(FinderMessage.id.asc()).limit(100).all()
    else:
        # Fetch the final bounded history then restore chronological order.
        messages = list(reversed(query.order_by(FinderMessage.id.desc()).limit(100).all()))
    return {
        "ok": True,
        "conversation": {
            "id": conversation.id,
            "status": conversation.status,
            "language": conversation.language,
            "revision": conversation.active_revision,
            "updated_at": conversation.updated_at.isoformat() + "Z" if conversation.updated_at else None,
        },
        "messages": [_serialize_message(db, message) for message in messages],
        "provider_mode": finder_provider_mode(),
    }


@router.get("/finder")
def finder_page(
    request: Request,
    conversation: Optional[int] = Query(None),
    conversation_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    requested_id = conversation_id if conversation_id is not None else conversation
    if requested_id is not None:
        _owned_conversation(db, user, requested_id)
    response = request.app.templates.TemplateResponse(
        request=request,
        name="finder.html",
        context={
            "request": request,
            "title": "Sevor Finder",
            "user": user,
            "session_user": request.session.get("user"),
            "csrf_token": get_or_create_csrf_token(request),
        },
    )
    response.headers["Cache-Control"] = "no-store, private"
    return response


@router.get("/api/finder/conversation")
def finder_conversation(
    request: Request,
    conversation_id: Optional[int] = Query(None),
    after_id: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    current_user = _require_user(user)
    conversation = _owned_conversation(db, current_user, conversation_id) if conversation_id is not None else None
    return JSONResponse(_conversation_payload(db, current_user, conversation, after_id=after_id), headers={"Cache-Control": "no-store"})


@router.post("/api/finder/conversation")
def finder_new_conversation(
    payload: FinderNewConversationPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    current_user = _require_user(user)
    require_csrf(request, payload.csrf_token)
    conversation = _create_conversation(db, current_user, request)
    db.commit()
    return JSONResponse(_conversation_payload(db, current_user, conversation), headers={"Cache-Control": "no-store"})


@router.post("/api/finder/message")
def finder_message(
    payload: FinderMessagePayload,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    current_user = _require_user(user)
    require_csrf(request, payload.csrf_token)
    _RATE_LIMITER.check(current_user.id)
    body = str(payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=422, detail="Describe what you want to rent.")
    if len(body) > MAX_FINDER_MESSAGE_CHARS:
        raise HTTPException(status_code=422, detail="Finder messages are too long.")
    client_message_id = validate_client_message_id(payload.client_message_id)
    conversation = _owned_conversation(db, current_user, payload.conversation_id) if payload.conversation_id else None
    # A lost response to the very first message has no conversation id to send
    # back. Find the user's existing client id before creating a second Finder
    # conversation or invoking parsing/search again.
    if conversation is None and client_message_id:
        existing = (
            db.query(FinderConversation)
            .join(FinderMessage, FinderMessage.conversation_id == FinderConversation.id)
            .filter(
                FinderConversation.user_id == current_user.id,
                FinderMessage.sender_role == "user",
                FinderMessage.client_message_id == client_message_id,
            )
            .first()
        )
        if existing:
            return JSONResponse(_conversation_payload(db, current_user, existing), headers={"Cache-Control": "no-store"})
    if conversation is None:
        conversation = _create_conversation(db, current_user, request)
    # Serialize mutations to a persisted search state. PostgreSQL honors this
    # row lock; SQLite safely ignores it in the isolated local test suite.
    conversation = (
        db.query(FinderConversation)
        .filter(FinderConversation.id == conversation.id, FinderConversation.user_id == current_user.id)
        .with_for_update()
        .one()
    )
    state = (
        db.query(FinderSearchState)
        .filter(FinderSearchState.conversation_id == conversation.id)
        .with_for_update()
        .one_or_none()
    ) or _state_for(db, conversation)
    if client_message_id:
        duplicate = (
            db.query(FinderMessage)
            .filter(
                FinderMessage.conversation_id == conversation.id,
                FinderMessage.client_message_id == client_message_id,
                FinderMessage.sender_role == "user",
            )
            .first()
        )
        if duplicate:
            return JSONResponse(_conversation_payload(db, current_user, conversation), headers={"Cache-Control": "no-store"})
    if payload.search_revision is not None and int(payload.search_revision) != int(state.revision or 0):
        raise HTTPException(status_code=409, detail="This Finder search changed. Please send your update again.")
    user_message = FinderMessage(
        conversation_id=conversation.id,
        sender_role="user",
        body=body,
        client_message_id=client_message_id,
    )
    db.add(user_message)
    db.flush()

    previous_spec = _spec_for(state, conversation.language)
    display = display_currency(request)
    next_spec, action = apply_user_turn(db, previous_spec, body, display_currency=display)
    support_requested = looks_like_support_request(body)
    provider_used = False
    # Finder prompts/results must stay separate from account, booking, or
    # payment support text. An explicit Support request never reaches the
    # optional Finder provider parser.
    if not support_requested:
        categories = [row[0] for row in public_listings_query(db).with_entities(Item.category).distinct().all()]
        locations = [row[0] for row in public_listings_query(db).with_entities(Item.city).filter(Item.city.isnot(None), Item.city != "").distinct().all()]
        next_spec, provider_used = enrich_spec_with_provider(
            next_spec,
            user_text=body,
            catalog_categories=categories,
            catalog_locations=locations,
        )
    next_spec.language = next_spec.language or conversation.language

    # An explicit account/booking/support request must not be swallowed by an
    # earlier rental-search context. Finder remains separate from Support, but
    # it can safely point the user to the existing support route without
    # creating or changing a ticket.
    if support_requested:
        answer, metadata = support_request_response(next_spec.language)
    elif action == "compare":
        answer, metadata = comparison_for_seen_listings(
            db,
            _seen_ids(state),
            parse_compare_positions(body),
            spec=next_spec,
        )
    else:
        result = None
        if action == "more":
            if int(state.next_offset or -1) < 0:
                answer = finder_copy(next_spec.language, "no_more")
                metadata = {
                    "kind": "search_result",
                    "spec": next_spec.to_dict(),
                    "search_summary": {"labels": [f"{row['key']}: {row['value']}" for row in spec_summary(next_spec)]},
                    "result_cards": [],
                    "near_cards": [],
                    "total_confirmed": 0,
                    "next_offset": None,
                    "has_more": False,
                }
            else:
                offset = int(state.next_offset)
        else:
            conversation.active_revision = int(conversation.active_revision or 0) + 1
            state.revision = conversation.active_revision
            next_spec.search_revision = state.revision
            offset = 0
        if action != "more" or int(state.next_offset or -1) >= 0:
            result = search_rentable_listings(db, next_spec, offset=offset)
            answer, metadata = make_assistant_search_message(next_spec, result, action=action)
            state.next_offset = int(result.next_offset) if result.next_offset is not None else -1
            old_seen = _seen_ids(state) if action == "more" else []
            state.last_result_ids_json = json.dumps(old_seen + [card["id"] for card in result.cards if card.get("id") not in old_seen], separators=(",", ":"))
        metadata["provider_parser_used"] = provider_used
    state.spec_json = json.dumps(next_spec.to_dict(), ensure_ascii=False, separators=(",", ":"))
    state.updated_at = datetime.utcnow()
    conversation.language = next_spec.language
    conversation.updated_at = datetime.utcnow()
    conversation.context_json = json.dumps({"language": next_spec.language, "summary": spec_summary(next_spec)}, ensure_ascii=False, separators=(",", ":"))
    assistant_message = FinderMessage(
        conversation_id=conversation.id,
        sender_role="assistant",
        body=answer,
        metadata_json=json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )
    db.add(assistant_message)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if client_message_id:
            existing_conversation = _owned_conversation(db, current_user, conversation.id)
            return JSONResponse(_conversation_payload(db, current_user, existing_conversation), headers={"Cache-Control": "no-store"})
        raise
    return JSONResponse(_conversation_payload(db, current_user, conversation), headers={"Cache-Control": "no-store"})
