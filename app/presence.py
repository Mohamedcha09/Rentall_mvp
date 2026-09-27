"""Small server-side presence helpers shared by SEVOR pages and Messages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models_metrics import OnlineSession


# The existing base-page heartbeat runs every 30 seconds.  A two-minute window
# tolerates mobile/browser scheduling delays without presenting stale activity
# as permanently online.
ONLINE_WINDOW_SECONDS = 120


def session_user_id(request) -> int | None:
    session_user = request.session.get("user") or {}
    if not isinstance(session_user, dict):
        return None
    try:
        value = int(session_user.get("id"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def iso_timestamp(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def user_presence(db: Session, user_id: int, *, now: datetime | None = None) -> dict[str, object]:
    """Return minimal participant presence; callers must authorize first."""
    current = now or datetime.utcnow()
    last_seen = (
        db.query(func.max(OnlineSession.last_seen))
        .filter(OnlineSession.user_id == user_id)
        .scalar()
    )
    online = bool(last_seen and last_seen >= current - timedelta(seconds=ONLINE_WINDOW_SECONDS))
    return {"online": online, "last_seen": iso_timestamp(last_seen)}
