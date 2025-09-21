# app/routes_users.py
# -*- coding: utf-8 -*-
"""
Routes for user public profile pages.
No HTML here; the template is templates/user.html.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Item

# Use the same templates directory as the rest of the app
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter()


def _utc_now():
    """Return an aware UTC datetime if possible."""
    try:
        return datetime.now(timezone.utc)
    except Exception:
        # Fallback (naive). We won't compare tz-aware with naive directly.
        return datetime.utcnow()


@router.get("/users/{user_id}")
def user_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Public user profile:
    - Basic info (first/last name, city, bio if present)
    - Badges: new (account age < 60 days), verified (is_verified)
    - Owner's active items (latest first)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # If user doesn't exist, go back to search (keeps q if present)
        q = request.query_params.get("q", "")
        return RedirectResponse(url=f"/search?q={q}", status_code=303)

    # Basic fields (safe-get: if column missing returns default)
    first_name = getattr(user, "first_name", "") or ""
    last_name = getattr(user, "last_name", "") or ""
    full_name = f"{first_name} {last_name}".strip() or (first_name or last_name or "User")
    city = getattr(user, "city", "") or ""
    bio = getattr(user, "bio", "") or ""
    status = getattr(user, "status", "") or ""
    avatar_path = getattr(user, "avatar_path", "") or ""
    created = getattr(user, "created_at", None)
    is_verified = bool(getattr(user, "is_verified", False))

    # "New" badge: account age < 60 days
    is_new_yellow = False
    if created:
        now = _utc_now()
        # Normalize to naive before subtraction if needed
        try:
            if getattr(created, "tzinfo", None) is not None:
                created_naive = created.astimezone(timezone.utc).replace(tzinfo=None)
                now_naive = now.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                created_naive = created
                now_naive = now.replace(tzinfo=None)
            is_new_yellow = (now_naive - created_naive).days < 60
        except Exception:
            is_new_yellow = False

    # Owner items (active only)
    items_q = db.query(Item).filter(
        Item.owner_id == user_id,
        Item.is_active == "yes",
    )
    items = items_q.order_by(desc(Item.created_at)).limit(24).all()
    items_count = items_q.count()

    # Ratings placeholders (adapt if you have a ratings table)
    rating_avg = 0.0
    rating_count = 0

    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "session_user": request.session.get("user"),
            "user_obj": user,            # full ORM object if template needs more
            "full_name": full_name,
            "city": city,
            "bio": bio,
            "status": status,
            "avatar_path": avatar_path,
            "created_at": created,
            "is_new_yellow": is_new_yellow,
            "is_verified": is_verified,
            "items": items,
            "items_count": items_count,
            "rating_avg": rating_avg,
            "rating_count": rating_count,
        },
    )
