# app/notifications.py
from __future__ import annotations
from typing import Optional
from datetime import datetime
import re
from urllib.parse import parse_qs, urlparse
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from .database import get_db
from .models import Booking, Item, Notification, SupportTicket, User

router = APIRouter(tags=["notifications"])

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None

def _json(data: dict) -> JSONResponse:
    return JSONResponse(data, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

_BOOKING_LINK_RE = re.compile(
    r"^/(?:bookings/flow|dm/deposits|deposits|f/payouts/(?:receipt|deposit))/(\d+)(?:/|$)"
)
_TICKET_LINK_RE = re.compile(r"^/(?:cs/chatbot|chatbot|support|cs|md|mod)/ticket/(\d+)(?:/|$)")
_ITEM_LINK_RE = re.compile(r"^/items/(\d+)(?:/|$)")


def _notification_link_context(link_url: str | None) -> tuple[str | None, int | None]:
    """Return only reliable, already-authorized context encoded in a notification link."""
    parsed = urlparse(link_url or "")
    path = parsed.path or ""

    for context_type, pattern in (
        ("booking", _BOOKING_LINK_RE),
        ("ticket", _TICKET_LINK_RE),
        ("item", _ITEM_LINK_RE),
    ):
        match = pattern.match(path)
        if match:
            return context_type, int(match.group(1))

    # Rejected-listing notifications use a one-time open route with the real item id in its query.
    if path.startswith("/notifications/open/"):
        raw_item_id = parse_qs(parsed.query).get("item_id", [None])[0]
        try:
            return "item", int(raw_item_id) if raw_item_id else None
        except (TypeError, ValueError):
            return None, None
    return None, None


def _public_actor_payload(actor: User | None) -> dict | None:
    if not actor:
        return None
    name = (getattr(actor, "full_name", "") or "").strip()
    if not name:
        name = " ".join(
            part for part in (getattr(actor, "first_name", ""), getattr(actor, "last_name", "")) if part
        ).strip()
    if not name:
        return None
    return {
        "name": name,
        "avatar_path": (getattr(actor, "avatar_path", None) or "").strip(),
    }


def _item_payload(item: Item | None) -> dict | None:
    if not item:
        return None
    image_path = (getattr(item, "image_path", None) or "").strip()
    if not image_path:
        image_urls = getattr(item, "image_urls", None)
        if isinstance(image_urls, (list, tuple)) and image_urls:
            image_path = str(image_urls[0] or "").strip()
    return {
        "title": (getattr(item, "title", None) or "").strip(),
        "image_path": image_path,
    }


def _booking_actor(notification: Notification, booking: Booking, recipient_id: int) -> User | None:
    """Resolve only actions whose actor is unambiguous from the actual producer behavior."""
    title = " ".join((notification.title or "").casefold().split())
    if title == "new booking request":
        actor = booking.renter
    elif title == "booking accepted":
        actor = booking.owner
    elif title in {"renter picked up the item", "return marked", "renter responded"}:
        actor = booking.renter
    elif title == "new deposit report":
        actor = booking.owner
    else:
        actor = None
    return actor if actor and actor.id != recipient_id else None


def _support_actor(notification: Notification, ticket: SupportTicket, recipient_id: int) -> User | None:
    """Customer identity is public to the support staff already assigned access to the ticket."""
    title = (notification.title or "").casefold()
    if "new support ticket" not in title and "new customer reply" not in title:
        return None
    actor = ticket.user
    return actor if actor and actor.id != recipient_id else None


def _notification_feed_items(rows: list[Notification], db: Session, recipient_id: int) -> list[dict]:
    """Batch optional presentation context for the feed; never modifies notification state."""
    contexts = {row.id: _notification_link_context(row.link_url) for row in rows}
    booking_ids = {context_id for kind, context_id in contexts.values() if kind == "booking" and context_id}
    ticket_ids = {context_id for kind, context_id in contexts.values() if kind == "ticket" and context_id}
    item_ids = {context_id for kind, context_id in contexts.values() if kind == "item" and context_id}

    bookings_by_id = {}
    if booking_ids:
        bookings_by_id = {
            booking.id: booking
            for booking in (
                db.query(Booking)
                .options(joinedload(Booking.renter), joinedload(Booking.owner), joinedload(Booking.item))
                .filter(Booking.id.in_(booking_ids))
                .all()
            )
        }
    tickets_by_id = {}
    if ticket_ids:
        tickets_by_id = {
            ticket.id: ticket
            for ticket in (
                db.query(SupportTicket)
                .options(joinedload(SupportTicket.user))
                .filter(SupportTicket.id.in_(ticket_ids))
                .all()
            )
        }
    items_by_id = {}
    if item_ids:
        items_by_id = {item.id: item for item in db.query(Item).filter(Item.id.in_(item_ids)).all()}

    feed_items = []
    for notification in rows:
        context_type, context_id = contexts.get(notification.id, (None, None))
        actor = None
        item = None
        if context_type == "booking":
            booking = bookings_by_id.get(context_id)
            if booking:
                actor = _booking_actor(notification, booking, recipient_id)
                item = booking.item
        elif context_type == "ticket":
            ticket = tickets_by_id.get(context_id)
            if ticket:
                actor = _support_actor(notification, ticket, recipient_id)
        elif context_type == "item":
            candidate = items_by_id.get(context_id)
            # Item notices are created for the owner; do not expose a thumbnail for an unrelated item.
            if candidate and candidate.owner_id == recipient_id:
                item = candidate

        entry = {
            "id": notification.id,
            "title": notification.title,
            "body": notification.body or "",
            "kind": notification.kind or "info",
            "link": notification.link_url or "",
            "is_read": bool(notification.is_read),
            "created_at": notification.created_at.isoformat(),
        }
        actor_payload = _public_actor_payload(actor)
        item_context = _item_payload(item)
        if actor_payload:
            entry["actor"] = actor_payload
        if item_context:
            entry["item"] = item_context
        feed_items.append(entry)
    return feed_items


# ========= helper: create a single notification =========
def push_notif(
    db: Session,
    user_id: int,
    title: str,
    body: str = "",
    *,
    kind: str = "info",
    link_url: str | None = None,
    do_commit: bool = True,           # <-- Important: commit by default
) -> Optional[Notification]:
    if not user_id or not (title or "").strip():
        return None
    n = Notification(
        user_id=user_id,
        title=(title or "").strip()[:200],
        body=(body or "").strip()[:1000],
        kind=kind or "info",
        link_url=link_url or "",
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    if do_commit:
        db.commit()
        try:
            db.refresh(n)
        except Exception:
            pass
    else:
        db.flush()
    return n

# ========= Old API (kept as-is) =========
@router.get("/api/notifs/unread_count")
def unread_count_legacy(
    request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)
):
    if not user:
        return JSONResponse({"count": 0})
    cnt = db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read == False
    ).count()
    return JSONResponse({"count": int(cnt)})

@router.get("/api/notifs/list")
def list_notifs_legacy(
    request: Request,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )
    return JSONResponse({"items": _notification_feed_items(rows, db, user.id)})

@router.post("/api/notifs/mark_all_read")
def mark_all_read_legacy(
    request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return JSONResponse({"ok": True})

# ========= ALIASES for the new frontend routes =========
# Even if the frontend hits /api/unread_count and /api/notifications/poll, they work from the same router

@router.get("/api/unread_count")
def api_unread_count(db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    if not user:
        return _json({"count": 0})
    count = db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read == False
    ).count()
    return _json({"count": int(count)})

@router.get("/api/notifications/poll")
def api_poll(
    request: Request,
    since: int = Query(0, description="Unix seconds of last poll"),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    cutoff = datetime.utcfromtimestamp(since or 0)
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.created_at > cutoff)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )
    items = [{
        "id": r.id,
        "title": r.title,
        "body": r.body or "",
        "url": r.link_url or "",
        "ts": int(r.created_at.timestamp()),
        "kind": r.kind or "system",
    } for r in rows]
    now = int(datetime.utcnow().timestamp())
    return _json({"now": now, "items": items})

@router.post("/api/notifications/{notif_id}/read")
def mark_read(
    notif_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    n = db.get(Notification, notif_id)
    if not n or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    n.is_read = True
    db.commit()
    return _json({"ok": True})


