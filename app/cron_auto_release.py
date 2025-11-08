# app/cron_auto_release.py
from __future__ import annotations
from datetime import datetime, timedelta
import os

import stripe
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, User
from .notifications_api import push_notification, notify_admins

# ===== SMTP Email (fallback) =====
# Will be replaced later by app/emailer.py; this guarantees no break if it's missing.
try:
    from .email_service import send_email

except Exception:
    def send_email(to, subject, html_body, text_body=None, cc=None, bcc=None, reply_to=None):
        return False  # Temporary NO-OP

BASE_URL = (os.getenv("SITE_URL") or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")

def _user_email(db: Session, user_id: int) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return (u.email or None) if u else None

def _admin_emails(db: Session) -> list[str]:
    q = db.query(User).filter(((User.role == "admin") | (User.is_deposit_manager == True))).all()
    return [getattr(a, "email", None) for a in q if getattr(a, "email", None)]

router = APIRouter(tags=["admin"])

# Stripe setup
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# Same time window: 48 hours after return
AUTO_RELEASE_WINDOW_HOURS = 48

# [Addition] Renter response deadline: 24h after DM decision with execution on timeout
DM_RESPONSE_WINDOW_HOURS = 24


# =======================
# Helpers
# =======================
def _currency(num: int) -> str:
    try:
        return f"{int(num):,}"
    except Exception:
        return str(num)


def _stripe_capture(pi_id: str, amount: int) -> bool:
    """
    Stripe expects amounts in cents, so we multiply by 100.
    """
    try:
        stripe.PaymentIntent.capture(pi_id, amount_to_capture=int(amount) * 100)
        return True
    except Exception:
        return False


def _stripe_cancel(pi_id: str) -> bool:
    try:
        stripe.PaymentIntent.cancel(pi_id)
        return True
    except Exception:
        return False


def _has_dispute_open(bk: Booking) -> bool:
    return (getattr(bk, "deposit_status", None) or "").lower() in (
        "in_dispute", "partially_withheld", "claimed"
    )


def _has_renter_replied(bk: Booking) -> bool:
    """
    The renter is considered to have replied if we have a timestamp of their response.
    (If you have additional logic based on renter-submitted evidence, you can extend this later.)
    """
    return getattr(bk, "renter_response_at", None) is not None


# ==========================
# Auto-release logic (48h)
# ==========================
def _can_auto_release(bk: Booking, now: datetime) -> bool:
    """
    Conditions:
      - Booking marked returned / in_review
      - There is a deposit authorization (deposit_hold_intent_id)
      - No open dispute
      - 48 hours have passed since returned_at with no report
    """
    if not getattr(bk, "returned_at", None):
        return False
    if _has_dispute_open(bk):
        return False
    if getattr(bk, "deposit_hold_intent_id", None) in (None, ""):
        return False
    if getattr(bk, "status", None) not in ("returned", "in_review"):
        return False

    try:
        deadline = bk.returned_at + timedelta(hours=AUTO_RELEASE_WINDOW_HOURS)
        return now >= deadline
    except Exception:
        return False


def _do_release(bk: Booking) -> None:
    """
    Cancels the deposit authorization and adjusts local states.
    """
    pi_id = getattr(bk, "deposit_hold_intent_id", None)
    if not pi_id:
        return

    # Try to cancel the hold on Stripe (safe: do not break job on any error)
    try:
        if stripe.api_key:
            stripe.PaymentIntent.cancel(pi_id)
    except Exception:
        # Quietly ignore—may have been cancelled already
        pass

    # Update deposit state and booking
    try:
        bk.deposit_status = "refunded"
        bk.deposit_charged_amount = 0
    except Exception:
        pass

    # If booking is still returned/in_review, consider it completed
    try:
        if getattr(bk, "status", None) in ("returned", "in_review"):
            bk.status = "completed"
    except Exception:
        pass

    # Timestamp update
    try:
        bk.updated_at = datetime.utcnow()
    except Exception:
        pass


# ======================================================
# Execute DM decision automatically after renter timeout (24h)
# ======================================================
def _can_execute_dm_decision(bk: Booking, now: datetime) -> bool:
    """
    Conditions for automatic execution after the response window:
      - There is a PaymentIntent (deposit hold)
      - There is a stored DM decision (bk.dm_decision: withhold/partial/release)
      - Current booking state: awaiting_renter (safety)
      - The renter did not reply before the deadline (renter_response_at == None)
      - bk.renter_response_deadline_at is set and has passed
      - Decision has not been executed before (dm_decision_at == None)
    """
    pi_id = getattr(bk, "deposit_hold_intent_id", None)
    decision = (getattr(bk, "dm_decision", None) or "").lower()
    deadline = getattr(bk, "renter_response_deadline_at", None)
    already_executed = getattr(bk, "dm_decision_at", None) is not None
    deposit_status = (getattr(bk, "deposit_status", None) or "").lower()

    if not pi_id:
        return False
    if decision not in ("withhold", "partial", "release"):
        return False
    # ✅ Only auto-execute when we're waiting for the renter
    if deposit_status != "awaiting_renter":
        return False
    # ✅ Stop auto-execution if the renter replied before deadline
    if _has_renter_replied(bk):
        return False
    if not deadline:
        return False
    if already_executed:
        return False

    try:
        return now >= deadline
    except Exception:
        return False


def _execute_dm_decision(db: Session, bk: Booking) -> str:
    """
    Executes the DM decision stored on the booking after the renter response window expires:
      - withhold/partial: capture dm_decision_amount (Stripe will automatically release the remainder)
      - release: cancel the deposit authorization
    Updates booking states and sends notifications to both parties.
    Returns a short text describing what happened.
    """
    pi_id = getattr(bk, "deposit_hold_intent_id", None)
    decision = (getattr(bk, "dm_decision", None) or "").lower()
    amount = int(getattr(bk, "dm_decision_amount", 0) or 0)
    deposit_total = int(
        (getattr(bk, "deposit_amount", None)
         or getattr(bk, "hold_deposit_amount", None)
         or 0)
    )

    if not pi_id or not decision:
        return "skipped:no_pi_or_decision"

    if decision in ("withhold", "partial"):
        if amount <= 0:
            return "skipped:zero_amount"

        ok = _stripe_capture(pi_id, amount)
        if not ok:
            return "error:stripe_capture_failed"

        # Update state
        try:
            bk.deposit_charged_amount = amount
            if deposit_total > 0 and amount >= deposit_total:
                bk.deposit_status = "claimed"
            else:
                bk.deposit_status = "partially_withheld"
            bk.status = "closed"
            bk.dm_decision_at = datetime.utcnow()
            bk.updated_at = datetime.utcnow()
        except Exception:
            pass

        db.commit()

        # Notifications
        try:
            push_notification(
                db, bk.owner_id,
                "Decision executed: deposit captured",
                f"You were compensated { _currency(amount) } from booking #{bk.id}'s deposit.",
                f"/bookings/flow/{bk.id}",
                "deposit",
            )
            push_notification(
                db, bk.renter_id,
                "Response window ended",
                f"{ _currency(amount) } was captured from your deposit for booking #{bk.id} due to no evidence submitted in time.",
                f"/bookings/flow/{bk.id}",
                "deposit",
            )
            notify_admins(db, "Auto-executed DM decision", f"Booking #{bk.id} — captured {amount}.", f"/dm/deposits/{bk.id}")
        except Exception:
            pass

        # ===== Emails: Auto-execution — capture =====
        try:
            owner_email = _user_email(db, bk.owner_id)
            renter_email = _user_email(db, bk.renter_id)
            admins_em   = _admin_emails(db)
            case_url = f"{BASE_URL}/bookings/flow/{bk.id}"
            amt_txt = _currency(amount)
            if owner_email:
                send_email(
                    owner_email,
                    f"Auto-executed capture — #{bk.id}",
                    f"<p>You were compensated {amt_txt} CAD from booking #{bk.id}'s deposit after the response window expired.</p>"
                    f'<p><a href="{case_url}">View booking</a></p>'
                )
            if renter_email:
                send_email(
                    renter_email,
                    f"Response window ended — {amt_txt} CAD captured — #{bk.id}",
                    f"<p>{amt_txt} CAD was captured from your deposit for booking #{bk.id} because no evidence was submitted within the deadline.</p>"
                    f'<p><a href="{case_url}">View booking</a></p>'
                )
            for em in admins_em:
                send_email(
                    em,
                    f"[Auto] DM decision executed — #{bk.id}",
                    f"<p>Auto-capture executed for {amt_txt} CAD.</p>"
                    f'<p><a href="{case_url}">Open case</a></p>'
                )
        except Exception:
            pass

        return f"captured:{amount}"

    elif decision == "release":
        ok = _stripe_cancel(pi_id)
        if not ok:
            # The hold may be expired or already cancelled — proceed with updates
            pass

        try:
            bk.deposit_status = "refunded"
            bk.deposit_charged_amount = 0
            bk.status = "closed"
            bk.dm_decision_at = datetime.utcnow()
            bk.updated_at = datetime.utcnow()
        except Exception:
            pass

        db.commit()

        try:
            push_notification(
                db, bk.owner_id,
                "Deposit released",
                f"The deposit for booking #{bk.id} has been returned after the response window expired.",
                f"/bookings/flow/{bk.id}",
                "deposit",
            )
            push_notification(
                db, bk.renter_id,
                "Deposit released",
                f"Your deposit for booking #{bk.id} has been returned after the response window expired.",
                f"/bookings/flow/{bk.id}",
                "deposit",
            )
            notify_admins(db, "Auto-executed DM decision", f"Booking #{bk.id} — full release.", f"/dm/deposits/{bk.id}")
        except Exception:
            pass

        # ===== Emails: Auto-execution — release =====
        try:
            owner_email = _user_email(db, bk.owner_id)
            renter_email = _user_email(db, bk.renter_id)
            admins_em   = _admin_emails(db)
            case_url = f"{BASE_URL}/bookings/flow/{bk.id}"
            if owner_email:
                send_email(
                    owner_email,
                    f"Auto-executed — deposit released — #{bk.id}",
                    f"<p>The deposit was fully released for this booking after the response window expired.</p>"
                    f'<p><a href="{case_url}">View booking</a></p>'
                )
            if renter_email:
                send_email(
                    renter_email,
                    f"Deadline passed — your deposit was released — #{bk.id}",
                    f"<p>Your deposit was fully released for this booking after the response window expired.</p>"
                    f'<p><a href="{case_url}">View booking</a></p>'
                )
            for em in admins_em:
                send_email(
                    em,
                    f"[Auto] DM execution: release — #{bk.id}",
                    f"<p>Deposit release executed automatically (deadline passed).</p>"
                    f'<p><a href="{case_url}">Open case</a></p>'
                )
        except Exception:
            pass

        return "released"

    return "skipped:unknown_decision"


@router.get("/admin/run/auto-release")
def run_auto_release(
    dry: bool = Query(True, description="Dry-run mode only; no real Stripe/DB changes"),
    db: Session = Depends(get_db),
):
    """
    Manually run auto-release from Admin during testing.
    - Iterates eligible bookings and cancels the deposit hold if 48 hours passed since return with no dispute.
    - If dry=true it makes no changes, only returns what it would do.

    [Addition]
    - Also auto-executes deferred DM decisions after the renter response deadline (24h),
      provided the status is awaiting_renter and the renter did not reply before the deadline.
    """
    now = datetime.utcnow()

    # -------------------------------
    # Original part: Auto Release 48h
    # -------------------------------
    q = (
        db.query(Booking)
        .filter(
            Booking.returned_at.isnot(None),
            Booking.deposit_hold_intent_id.isnot(None),
            Booking.deposit_status.is_(None) | Booking.deposit_status.in_(["held", "refunded", "none", "in_review"]),
            Booking.status.in_(["returned", "in_review"]),
        )
        .order_by(Booking.returned_at.asc())
    )
    candidates = q.all()
    to_release = [bk for bk in candidates if _can_auto_release(bk, now)]

    released_count = 0
    released_ids = []

    if not dry:
        for bk in to_release:
            _do_release(bk)
            db.commit()
            released_count += 1
            released_ids.append(bk.id)

            # Notifications to booking parties
            try:
                push_notification(
                    db,
                    bk.renter_id,
                    "Automatic deposit release",
                    f"Your deposit for booking #{bk.id} was automatically released after the objection window ended.",
                    f"/bookings/flow/{bk.id}",
                    "deposit",
                )
                push_notification(
                    db,
                    bk.owner_id,
                    "Automatic deposit release",
                    f"The deposit for booking #{bk.id} was automatically released after the window ended.",
                    f"/bookings/flow/{bk.id}",
                    "deposit",
                )
            except Exception:
                pass

            # ===== Emails: 48h auto-release =====
            try:
                renter_email = _user_email(db, bk.renter_id)
                owner_email  = _user_email(db, bk.owner_id)
                admins_em    = _admin_emails(db)
                case_url = f"{BASE_URL}/bookings/flow/{bk.id}"
                if renter_email:
                    send_email(
                        renter_email,
                        f"Automatic deposit release — #{bk.id}",
                        f"<p>Your deposit was automatically released after 48 hours with no dispute.</p>"
                        f'<p><a href="{case_url}">View booking</a></p>'
                    )
                if owner_email:
                    send_email(
                        owner_email,
                        f"Deposit released — #{bk.id}",
                        f"<p>The deposit was automatically released after the window ended.</p>"
                        f'<p><a href="{case_url}">View booking</a></p>'
                    )
                for em in admins_em:
                    send_email(
                        em,
                        f"[Auto] 48h deposit release — #{bk.id}",
                        f"<p>The deposit for this booking was auto-released due to no dispute within the window.</p>"
                        f'<p><a href="{case_url}">Open booking</a></p>'
                    )
            except Exception:
                pass

        try:
            if released_count:
                notify_admins(
                    db,
                    "Auto-release run",
                    f"Automatically released {released_count} deposits. (IDs: {released_ids})",
                    "/admin",
                )
        except Exception:
            pass

    # -------------------------------------------------------
    # Execute DM decisions after renter deadline (24h)
    # -------------------------------------------------------
    q2 = (
        db.query(Booking)
        .filter(
            Booking.deposit_hold_intent_id.isnot(None),
            Booking.renter_response_deadline_at.isnot(None),
        )
        .order_by(Booking.renter_response_deadline_at.asc())
    )
    dm_candidates = q2.all()
    dm_eligible = [bk for bk in dm_candidates if _can_execute_dm_decision(bk, now)]

    dm_results = {}
    if not dry:
        for bk in dm_eligible:
            res = _execute_dm_decision(db, bk)
            dm_results[bk.id] = res

    return {
        "now": now.isoformat(),
        "dry": dry,
        # original section
        "candidates": [bk.id for bk in candidates],
        "eligible": [bk.id for bk in to_release],
        "released_count": (released_count if not dry else 0),
        "released_ids": (released_ids if not dry else []),
        "window_hours": AUTO_RELEASE_WINDOW_HOURS,
        # additions for DM decisions
        "dm_candidates": [bk.id for bk in dm_candidates],
        "dm_eligible": [bk.id for bk in dm_eligible],
        "dm_window_hours": DM_RESPONSE_WINDOW_HOURS,
        "dm_results": (dm_results if not dry else {}),
    }
