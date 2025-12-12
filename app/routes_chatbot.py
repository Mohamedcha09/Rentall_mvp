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
    return JSONResponse(content=load_tree())


# ===========================================================
# CHATBOT PAGE
# ===========================================================
@router.get("/chatbot")
def chatbot_page(
    request: Request,
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    # last open chatbot ticket
    active_ticket = None
    
    return templates.TemplateResponse("chatbot.html", {
        "request": request,
        "user": user,
        "session_user": user,
        "active_ticket": active_ticket,
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
    answer: str = Form(...),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    t = SupportTicket(
        user_id=user.id,
        subject="Chatbot Assistance Needed",
        queue="cs_chatbot",
        status="open",
        last_from="user",
        unread_for_agent=True,
        unread_for_user=False,
        channel="chatbot",
        created_at=datetime.utcnow(),
    )
    db.add(t)
    db.flush()

    msg = SupportMessage(
        ticket_id=t.id,
        sender_id=user.id,
        sender_role="user",
        body=f"Chatbot question:\n{question}\n\nChatbot answer:\n{answer}\n\nUser clicked NO.",
        channel="chatbot",
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    db.commit()

    # notify CS agents
    agents = db.query(User).filter(User.is_support == True).all()
    for ag in agents:
        push_notification(
            db,
            ag.id,
            "🤖 Chatbot escalation",
            f"User needs help (ticket #{t.id})",
            url=f"/cs/chatbot/ticket/{t.id}",
            kind="support",
        )

    return {"ok": True, "ticket_id": t.id}


# ===========================================================
# TRANSFER TICKET
# ===========================================================
@router.post("/chatbot/ticket/{ticket_id}/transfer")
def chatbot_transfer_ticket(
    ticket_id: int,
    new_queue: str = Form(...),
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user or not user.is_support:
        raise HTTPException(status_code=403, detail="Not allowed")

    t = db.query(SupportTicket).filter_by(id=ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if t.status == "closed":
        raise HTTPException(status_code=400, detail="Ticket already closed")

    now = datetime.utcnow()

    transfer_map = {
        "cs_chatbot": "Your conversation has been transferred to our Customer Support team.",
        "md_chatbot": "Your conversation has been transferred to our Management Desk.",
        "mod_chatbot": "Your conversation has been transferred to our Moderation Team.",
    }

    if new_queue not in transfer_map:
        raise HTTPException(status_code=400, detail="Invalid queue")

    db.add(SupportMessage(
        ticket_id=ticket_id,
        sender_id=user.id,
        sender_role="system",
        body=transfer_map[new_queue],
        channel="chatbot",
        created_at=now,
    ))

    t.queue = new_queue
    t.last_from = "system"
    t.unread_for_user = True
    t.unread_for_agent = True
    t.updated_at = now

    # who receives the ticket?
    if new_queue == "cs_chatbot":
        target_filter = User.is_support == True
    else:
        target_filter = User.is_mod == True

    agents = db.query(User).filter(target_filter).all()

    for ag in agents:
        push_notification(
            db,
            ag.id,
            "🤖 Ticket transferred",
            f"Ticket #{ticket_id} moved to your team.",
            url=f"/{new_queue.replace('_chatbot','')}/chatbot/ticket/{ticket_id}",
            kind="support",
        )

    db.commit()
    return {"ok": True, "queue": new_queue}


# ===========================================================
# CLOSE TICKET
# ===========================================================
@router.post("/chatbot/ticket/{ticket_id}/close")
def chatbot_close_ticket(
    ticket_id: int,
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    # Only support / md / mod can close
    if not (user.is_support or user.is_mod):
        raise HTTPException(status_code=403, detail="Not allowed")

    t = db.query(SupportTicket).filter_by(id=ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if t.status == "resolved":
        return {"ok": True, "status": "already_resolved"}


    now = datetime.utcnow()

    closer_name = (
        (user.full_name or "").strip()
        or (user.first_name or "").strip()
        or (user.email or "").strip()
        or "support agent"
    )

    # SYSTEM message with closer name
    db.add(SupportMessage(
        ticket_id=ticket_id,
        sender_id=user.id,
        sender_role="system",
        body=f"This ticket has been closed by {closer_name}.",
        channel="chatbot",
        created_at=now,
    ))

    # Update ticket
    t.status = "resolved"            # ← أهم تعديل
    t.closed_by = closer_name
    t.closed_at = now
    t.last_from = "system"
    t.unread_for_user = True
    t.unread_for_agent = False
    t.updated_at = now

    db.commit()

    return {"ok": True, "status": "resolved", "closed_by": closer_name}



# ===========================================================
# LIVE AGENT DETECTION
# ===========================================================
@router.get("/api/chatbot/agent_status/{ticket_id}")
def chatbot_agent_status(
    ticket_id: int,
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    t = db.query(SupportTicket).filter_by(id=ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    last_msg = (
        db.query(SupportMessage)
        .filter_by(ticket_id=ticket_id)
        .order_by(SupportMessage.id.desc())
        .first()
    )

    agent_name = None

    if last_msg and last_msg.sender_role in ("support", "agent"):
        u = db.query(User).filter_by(id=last_msg.sender_id).first()
        if u:
            agent_name = u.full_name or u.first_name or "Support agent"

    return {
        "ticket_id": ticket_id,
        "assigned": bool(agent_name),
        "agent_name": agent_name,
    }


# ===========================================================
# GET MESSAGES FOR CHATBOT POLLING
# ===========================================================
@router.get("/api/chatbot/messages/{ticket_id}")
def chatbot_get_messages(
    ticket_id: int,
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    t = db.query(SupportTicket).filter_by(id=ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    msgs = (
        db.query(SupportMessage)
        .filter_by(ticket_id=ticket_id)
        .order_by(SupportMessage.id.asc())
        .all()
    )

    out = []
    for m in msgs:
        out.append({
            "id": m.id,
            "body": m.body,
            "sender_role": m.sender_role,
            "created_at": m.created_at.isoformat(),
        })

    return {
        "ok": True,
        "messages": out,
        "ticket_status": t.status,                   # 👈 مهم
        "closed_by": t.closed_by or None,           # 👈 مهم
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
    }


# ===========================================================
# SEND MESSAGE (USER → AGENT)
# ===========================================================
@router.post("/api/chatbot/messages/{ticket_id}")
def chatbot_send_message(
    ticket_id: int,
    body: str = Form(...),
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    t = db.query(SupportTicket).filter_by(id=ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if t.status == "closed":
        raise HTTPException(status_code=403, detail="Ticket is closed")

    msg = SupportMessage(
        ticket_id=ticket_id,
        sender_id=user.id,
        sender_role="user",
        body=body,
        channel="chatbot",
        created_at=datetime.utcnow(),
    )

    db.add(msg)

    t.last_from = "user"
    t.unread_for_agent = True
    t.updated_at = datetime.utcnow()

    db.commit()

    return {"ok": True}


# ===========================================================
# CLIENT VIEW FOR CHATBOT TICKET  (/chatbot/ticket/{id})
# ===========================================================
@router.get("/chatbot/ticket/{ticket_id}")
def chatbot_ticket_client(
    ticket_id: int,
    request: Request,
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    # fetch ticket
    t = db.query(SupportTicket).filter_by(id=ticket_id, user_id=user.id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # messages
    msgs = (
        db.query(SupportMessage)
        .filter_by(ticket_id=ticket_id)
        .order_by(SupportMessage.id.asc())
        .all()
    )

    return templates.TemplateResponse("chatbot_ticket_client.html", {
        "request": request,
        "ticket": t,
        "msgs": msgs,
        "user": user,
        "session_user": user,
    })

# ===========================================================
# CLIENT VIEW — CHATBOT TICKET PAGE
# ===========================================================
@router.get("/support/chatbot/ticket/{ticket_id}")
def chatbot_ticket_client_page(
    ticket_id: int,
    request: Request,
    db = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    t = db.query(SupportTicket).filter_by(id=ticket_id, channel="chatbot").first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # التذكرة يجب أن تكون للعميل نفسه
    if t.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    msgs = (
        db.query(SupportMessage)
        .filter_by(ticket_id=t.id)
        .order_by(SupportMessage.id.asc())
        .all()
    )

    return templates.TemplateResponse("chatbot_ticket_client.html", {
        "request": request,
        "user": user,
        "session_user": user,
        "ticket": t,
        "msgs": msgs,
        "display_currency": display_currency,
    })
