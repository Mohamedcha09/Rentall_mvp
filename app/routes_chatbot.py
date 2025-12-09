# app/routes_chatbot.py

from fastapi import APIRouter, HTTPException, Request, Depends, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
import os
import json
from functools import lru_cache
from typing import Optional
from datetime import datetime

from .utils import display_currency
from .auth import get_current_user
from .models import User, SupportTicket, SupportMessage
from .database import get_db
from .notifications_api import push_notification

router = APIRouter(tags=["chatbot"])

templates = Jinja2Templates(directory="app/templates")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TREE_PATH = os.path.join(BASE_DIR, "chatbot", "tree.json")


# ===========================================================
# LOAD TREE.JSON
# ===========================================================
@lru_cache(maxsize=1)
def load_tree():
    if not os.path.exists(TREE_PATH):
        raise FileNotFoundError(f"tree.json not found at {TREE_PATH}")
    with open(TREE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/chatbot/tree")
def get_chatbot_tree():
    try:
        return JSONResponse(content=load_tree())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# CHATBOT PAGE
# ===========================================================
@router.get("/chatbot")
def chatbot_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    return templates.TemplateResponse("chatbot.html", {
        "request": request,
        "user": user,
        "session_user": user,
        "display_currency": display_currency
    })


# ===========================================================
# OPEN NEW CHATBOT TICKET
# ===========================================================
@router.post("/chatbot/support")
def chatbot_open_ticket(
    request: Request,
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    question: str = Form(...),
    answer: str = Form(...)
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    # Create ticket
    t = SupportTicket(
        user_id=user.id,
        subject="Chatbot Assistance Needed",
        queue="cs_chatbot",
        status="new",
        last_from="user",
        unread_for_agent=True,
        unread_for_user=False,
        channel="chatbot",
    )
    db.add(t)
    db.flush()

    # First message
    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=user.id,
        sender_role="user",
        body=f"Chatbot question:\n{question}\n\nChatbot answer:\n{answer}\n\nUser clicked NO.",
        channel="chatbot"
    )
    db.add(msg)
    db.commit()

    # Notify CS agents
    agents = db.query(User).filter(User.is_support == True).all()
    for ag in agents:
        push_notification(
            db,
            ag.id,
            "🤖 Chatbot escalation",
            f"User needs help (ticket #{t.id})",
            url=f"/cs/chatbot/ticket/{t.id}",
            kind="support"
        )

    return {"ok": True, "ticket_id": t.id}


# ===========================================================
# TRANSFER SYSTEM (CS → MD → MOD)
# ===========================================================
@router.post("/chatbot/ticket/{ticket_id}/transfer")
def chatbot_transfer_ticket(
    ticket_id: int,
    new_queue: str = Form(...),  # cs_chatbot / md_chatbot / mod_chatbot
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user or not user.is_support:
        raise HTTPException(status_code=403, detail="Not allowed")

    t = db.query(SupportTicket).filter_by(id=ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    now = datetime.utcnow()

    # Create system message text
    if new_queue == "cs_chatbot":
        transfer_text = "Your conversation has been transferred to our Customer Support team."
    elif new_queue == "md_chatbot":
        transfer_text = "Your conversation has been transferred to our Management Desk."
    elif new_queue == "mod_chatbot":
        transfer_text = "Your conversation has been transferred to our Moderation Team."
    else:
        raise HTTPException(status_code=400, detail="Invalid queue name")

    # Add system message
    db.add(SupportMessage(
        ticket_id=ticket_id,
        sender_id=user.id,
        sender_role="system",
        body=transfer_text,
        channel="chatbot",
        created_at=now
    ))

    # Update ticket metadata
    t.queue = new_queue
    t.last_from = "system"
    t.unread_for_user = True
    t.unread_for_agent = True
    t.updated_at = now

    # Determine which team receives ticket
    if new_queue == "cs_chatbot":
        target_filter = User.is_support == True
    elif new_queue == "md_chatbot":
        target_filter = User.is_mod == True  # No is_md field → using is_mod
    elif new_queue == "mod_chatbot":
        target_filter = User.is_mod == True

    agents = db.query(User).filter(target_filter).all()

    # Notify team members
    for ag in agents:
        push_notification(
            db,
            ag.id,
            "🤖 Ticket transferred",
            f"Ticket #{ticket_id} moved to your team.",
            url=f"/{new_queue.replace('_chatbot','')}/chatbot/ticket/{ticket_id}",
            kind="support"
        )

    db.commit()
    return {"ok": True, "queue": new_queue}


# ===========================================================
# 🔥 LIVE AGENT DETECTION API (Used by chatbot.js)
# ===========================================================
@router.get("/api/chatbot/agent_status/{ticket_id}")
def chatbot_agent_status(
    ticket_id: int,
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    Used by JS polling:
    - Did an agent join the ticket?
    - What is the agent's name?
    """

    t = db.query(SupportTicket).filter_by(id=ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Get last message of ticket
    last_msg = (
        db.query(SupportMessage)
        .filter_by(ticket_id=ticket_id)
        .order_by(SupportMessage.id.desc())
        .first()
    )

    agent_name = None

    # If last message belongs to agent → agent joined
    if last_msg and last_msg.sender_role in ("support", "agent"):
        u = db.query(User).filter_by(id=last_msg.sender_id).first()
        if u:
            agent_name = u.full_name or u.first_name or "Support agent"

    return {
        "ticket_id": ticket_id,
        "assigned": bool(agent_name),
        "agent_name": agent_name
    }
