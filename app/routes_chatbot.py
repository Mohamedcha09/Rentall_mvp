# app/routes_chatbot.py

from fastapi import APIRouter, HTTPException, Request, Depends, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
import os
import json
from functools import lru_cache
from typing import Optional

from .utils import display_currency
from .auth import get_current_user
from .models import User, SupportTicket, SupportMessage
from .database import get_db
from .notifications_api import push_notification

router = APIRouter(tags=["chatbot"])

templates = Jinja2Templates(directory="app/templates")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TREE_PATH = os.path.join(BASE_DIR, "chatbot", "tree.json")


# ============================
# Load chatbot tree
# ============================
@lru_cache(maxsize=1)
def load_tree():
    if not os.path.exists(TREE_PATH):
        raise FileNotFoundError(f"tree.json not found at {TREE_PATH}")
    with open(TREE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/chatbot/tree")
def get_chatbot_tree():
    try:
        data = load_tree()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================
# Chatbot main page
# ============================
@router.get("/chatbot")
def chatbot_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user)
):
    return templates.TemplateResponse("chatbot.html", {
        "request": request,
        "user": user,
        "session_user": user,
        "display_currency": display_currency
    })


# =======================================================
# NEW: When chatbot user presses "NO → Contact Support"
# =======================================================
@router.post("/chatbot/support")
def chatbot_open_ticket(
    request: Request,
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    question: str = Form(...),
    answer: str = Form(...)
):
    """
    Creates a special ticket when Chatbot → Contact Support.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    # Create ticket
    t = SupportTicket(
        user_id=user.id,
        subject="Chatbot Assistance Needed",
        queue="cs",
        status="new",
        last_from="user",
        unread_for_agent=True,
        unread_for_user=False
    )
    db.add(t)
    db.flush()

    # Save chatbot conversation as the first message
    body_text = f"Chatbot question:\n{question}\n\nChatbot answer given:\n{answer}\n\nUser clicked: NO (needs help)"
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=user.id,
        sender_role="user",
        body=body_text
    )
    db.add(msg)
    db.commit()

    # Notify support agents
    agents = (
        db.query(User)
        .filter(User.is_support == True, User.status == "approved")
        .all()
    )
    for ag in agents:
        push_notification(
            db,
            ag.id,
            "🤖 Chatbot escalation",
            f"User needs help (ticket #{t.id})",
            url=f"/cs/ticket/{t.id}",
            kind="support"
        )

    return {"ok": True, "ticket_id": t.id}
