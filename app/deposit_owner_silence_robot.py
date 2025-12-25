# app/deposit_owner_silence_robot.py
"""
Robot #1 — Owner Silence (After Return)
======================================
Goal:
- After renter submits return check (return_check_submitted_at)
- If owner does NOT open a dispute within the window
- Auto refund 100% of the deposit to renter via PayPal
- Log the action
- Close the deposit case

This robot:
✅ Executes only (doesn't decide)
✅ PayPal only (safe filter)
❌ Does NOT pay owner compensation
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog
from app.pay_api import send_deposit_refund


# -----------------------------
# Window config
# -----------------------------
DEFAULT_HOURS = 24

def _window_delta() -> timedelta:
    """
    Priority:
    - OWNER_SILENCE_WINDOW_SECONDS (tests)
    - OWNER_SILENCE_WINDOW_HOURS (prod)
    """
    sec = os.getenv("OWNER_SILENCE_WINDOW_SECONDS")
    if sec:
        try:
            s = int(sec)
            if s > 0:
                return timedelta(seconds=s)
        except Exception:
            pass

    hrs = os.getenv("OWNER_SILENCE_WINDOW_HOURS")
    if hrs:
        try:
            h = int(hrs)
            if h > 0:
                return timedelta(hours=h)
        except Exception:
            pass

    return timedelta(hours=DEFAULT_HOURS)


# -----------------------------
# Candidate selection
# -----------------------------
def find_candidates(db: Session) -> List[Booking]:
    """
    We want bookings that:
    - deposit exists
    - not refunded yet
    - renter submitted return check + marked "no problem"
    - owner did NOT open dispute
    - enough time has passed
    - PayPal only + capture id exists
    """
    now = datetime.utcnow()
    deadline = now - _window_delta()

    q = (
        db.query(Booking)
        .filter(
            Booking.deposit_amount > 0,
            Booking.deposit_refund_sent == False,

            # renter finished return step
            Booking.return_check_no_problem == True,
            Booking.return_check_submitted_at.isnot(None),
            Booking.return_check_submitted_at <= deadline,

            # owner stayed silent (no dispute)
            Booking.owner_dispute_opened_at.is_(None),

            # avoid conflicting deposit states
            and_(
                (Booking.deposit_status.is_(None)) |
                (~Booking.deposit_status.in_(["in_dispute", "awaiting_renter"]))
            ),

            # PayPal safe filters
            Booking.payment_method == "paypal",
            Booking.payment_provider.isnot(None),
        )
    )

    return q.all()


def compute_refund_amount(bk: Booking) -> float:
    # Full deposit refund for owner silence
    try:
        return float(bk.deposit_amount or 0)
    except Exception:
        return 0.0


# -----------------------------
# Execute
# -----------------------------
def execute_one(db: Session, bk: Booking) -> Optional[str]:
    refund_amount = compute_refund_amount(bk)
    if refund_amount <= 0:
        return None

    # extra safety
    capture_id = (bk.payment_provider or "").strip()
    if not capture_id or capture_id.lower() == "paypal":
        return None

    # Send real refund
    refund_id = send_deposit_refund(
        db=db,
        booking=bk,
        amount=refund_amount,
    )

    now = datetime.utcnow()

    # Update deposit case state (safe + minimal)
    try:
        bk.deposit_status = "refunded"
    except Exception:
        pass

    try:
        bk.status = "closed"
    except Exception:
        pass

    # Robot markers (if columns exist)
    try:
        setattr(bk, "deposit_auto_release_at", now)
    except Exception:
        pass

    try:
        setattr(bk, "auto_finalized_by_robot", True)
    except Exception:
        pass

    try:
        setattr(bk, "deposit_case_closed", True)
    except Exception:
        pass

    # Audit log
    db.add(
        DepositAuditLog(
            booking_id=bk.id,
            actor_id=0,
            actor_role="system",
            action="auto_refund_owner_silent",
            amount=int(refund_amount),
            reason="Owner did not open a dispute within the allowed window",
            details=f"refund_id={refund_id}",
        )
    )

    db.commit()
    return refund_id


def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)
        print("======================================")
        print("Robot #1 — Owner Silence (LIVE MODE)")
        print(f"Window: {_window_delta()}")
        print(f"Candidates found: {len(items)}")

        for bk in items:
            print(f"- Booking #{bk.id}: deposit={bk.deposit_amount} submitted_at={bk.return_check_submitted_at}")
            rid = execute_one(db, bk)
            if rid:
                print(f"  ✅ refunded: refund_id={rid}")
            else:
                print("  ⏭️ skipped (safety filters)")

        print("Robot finished.")
        print("======================================")

    except Exception as e:
        print("❌ Robot error:", str(e))
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_once()
