# app/deposit_manager.py
from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, User
from .notifications_api import push_notification
from .email_service import send_email

router = APIRouter(tags=["deposit-manager"])

# --------------- Helpers ---------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    data = request.session.get("user") or {}
    uid = data.get("id")
    return db.get(User, uid) if uid else None

def require_auth(user: Optional[User]):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

def require_manager(user: Optional[User]):
    require_auth(user)
    if not user.can_manage_deposits:
        raise HTTPException(status_code=403, detail="Deposit manager only")

def _get_booking(db: Session, booking_id: int) -> Booking:
    bk = db.get(Booking, booking_id)
    if not bk:
        raise HTTPException(status_code=404, detail="Booking not found")
    return bk


# --------------- Cases list ---------------
@router.get("/deposit-manager")
def dm_index(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
    view: Literal["pending", "in_review", "resolved"] = "pending",
):
    """
    Simple tabs:
      - pending   : cases that need a decision (deposit_status in ['in_dispute','held']) and booking is not closed
      - in_review : booking has status in_review (open and under review)
      - resolved  : booking is closed/completed and has a final deposit decision
    """
    require_manager(user)

    q = db.query(Booking)

    if view == "pending":
        q = q.filter(
            Booking.status.in_(["returned", "in_review"]),
            Booking.deposit_status.in_(["in_dispute", "held"])
        )
        title = "Deposit Queue — Pending"
    elif view == "in_review":
        q = q.filter(Booking.status == "in_review")
        title = "Deposit Queue — In Review"
    else:
        q = q.filter(Booking.status.in_(["closed", "completed"]))
        title = "Deposit Queue — Resolved"

    rows = q.order_by(Booking.updated_at.desc().nullslast(), Booking.created_at.desc().nullslast()).all()

    # Pass everything to the template
    return request.app.templates.TemplateResponse(
        "deposit_manager_index.html",
        {
            "request": request,
            "title": title,
            "session_user": request.session.get("user"),
            "rows": rows,
            "view": view,
        }
    )


# --------------- Claim the case ---------------
@router.post("/deposit-manager/{booking_id}/claim")
def dm_claim(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """
    Mark the case as under review (we don't add new columns; we just set status=in_review)
    """
    require_manager(user)
    bk = _get_booking(db, booking_id)

    # Logical states for claiming
    if bk.deposit_status not in ["in_dispute", "held"]:
        return RedirectResponse(url="/deposit-manager?view=resolved", status_code=303)

    bk.status = "in_review"
    bk.updated_at = datetime.utcnow()
    db.commit()

    # Notify both parties that the case is now under review
    push_notification(
        db, bk.owner_id, "Deposit case under review",
        f"Case #{bk.id} has been claimed by the deposit manager.",
        f"/bookings/flow/{bk.id}", "deposit"
    )
    push_notification(
        db, bk.renter_id, "Deposit case under review",
        f"Case #{bk.id} has been claimed by the deposit manager.",
        f"/bookings/flow/{bk.id}", "deposit"
    )

    return RedirectResponse(url="/deposit-manager?view=in_review", status_code=303)


# --------------- Request more info/evidence ---------------
@router.post("/deposit-manager/{booking_id}/need-info")
def dm_need_info(
    booking_id: int,
    target: Literal["owner", "renter"] = Form(...),
    message: str = Form("Please provide additional information/photos to support your position."),
    request: Request = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    require_manager(user)
    bk = _get_booking(db, booking_id)

    # Keep status as in_review
    bk.updated_at = datetime.utcnow()
    db.commit()

    # Send a notification to the requested party
    target_user_id = bk.owner_id if target == "owner" else bk.renter_id
    push_notification(
        db, target_user_id, "Additional information requested",
        message or "Please provide more details.",
        f"/bookings/flow/{bk.id}", "deposit"
    )

    return RedirectResponse(url="/deposit-manager?view=in_review", status_code=303)


# --------------- Execute the final decision (redirects to the decision route in routes_deposits.py) ---------------
@router.post("/deposit-manager/{booking_id}/decide")
def dm_decide(
    booking_id: int,
    decision: Literal["refund_all", "refund_partial", "withhold_all"] = Form(...),
    amount: int = Form(0),
    reason: str = Form(""),
    request: Request = None,
    user: Optional[User] = Depends(get_current_user),
):
    """
    We use the decision route written in routes_deposits.py.
    We only redirect the POST to /dm/deposits/{booking_id}/decision
    using 307 to preserve the same request method (POST) and the same form body.
    """
    require_manager(user)

    # Important: 307 preserves POST and the body; we don't put values in the QueryString
    return RedirectResponse(
        url=f"/dm/deposits/{booking_id}/decision",
        status_code=307
    )
