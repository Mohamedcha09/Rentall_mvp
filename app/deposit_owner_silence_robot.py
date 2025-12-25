# app/deposit_owner_silence_robot.py
"""
Robot #1 — Owner Silence (After Return)
======================================
TEST MODE (1 MINUTE)

Goal:
- After renter submits return check
- If owner does NOT open a dispute within 1 minute (TEST)
- Auto refund 100% of the deposit to renter via PayPal
- Send notifications:
    - Owner: deposit refunded due to silence
    - Renter: deposit refunded successfully
- Log the action
- Close the deposit case
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification


# =====================================================
# ⏱️ TEST WINDOW — 1 MINUTE ONLY
# =====================================================
WINDOW_DELTA = timedelta(minutes=1)


# =====================================================
# Find eligible bookings
# =====================================================
def find_candidates(db: Session) -> List[Booking]:
    now = datetime.utcnow()
    deadline = now - WINDOW_DELTA

    return (
        db.query(Booking)
        .filter(
            Booking.deposit_amount > 0,
            Booking.deposit_refund_sent == False,

            # renter finished return
            Booking.return_check_no_problem == True,
            Booking.return_check_submitted_at.isnot(None),
            Booking.return_check_submitted_at <= deadline,

            # owner silence
            Booking.owner_dispute_opened_at.is_(None),

            # avoid conflict states
            and_(
                (Booking.deposit_status.is_(None)) |
                (~Booking.deposit_status.in_(["in_dispute", "awaiting_renter"]))
            ),

            # PayPal only
            Booking.payment_method == "paypal",
            Booking.payment_provider.isnot(None),
        )
        .all()
    )


def compute_refund_amount(bk: Booking) -> float:
    try:
        return float(bk.deposit_amount or 0)
    except Exception:
        return 0.0


# =====================================================
# Execute refund + notifications
# =====================================================
def execute_one(db: Session, bk: Booking) -> Optional[str]:
    refund_amount = compute_refund_amount(bk)
    if refund_amount <= 0:
        return None

    capture_id = (bk.payment_provider or "").strip()
    if not capture_id or capture_id.lower() == "paypal":
        return None

    # 🔥 Send PayPal refund
    refund_id = send_deposit_refund(
        db=db,
        booking=bk,
        amount=refund_amount,
    )

    now = datetime.utcnow()

    # Update booking state
    bk.deposit_status = "refunded"
    bk.deposit_refund_sent = True
    bk.deposit_case_closed = True
    bk.status = "closed"

    # 🧾 Audit log
    db.add(
        DepositAuditLog(
            booking_id=bk.id,
            actor_id=0,
            actor_role="system",
            action="auto_refund_owner_silent",
            amount=int(refund_amount),
            reason="Owner did not open a dispute within 1 minute (TEST)",
            details=f"refund_id={refund_id}",
        )
    )

    db.commit()

    # =================================================
    # 🔔 Notifications
    # =================================================

    # 📩 Notify renter
    push_notification(
        user_id=bk.renter_id,
        title="Deposit refunded ✅",
        message="Your deposit has been fully refunded successfully.",
        data={"booking_id": bk.id},
    )

    # 📩 Notify owner
    push_notification(
        user_id=bk.owner_id,
        title="Deposit refunded to renter",
        message="The deposit was refunded to the renter due to no dispute being opened within the allowed time.",
        data={"booking_id": bk.id},
    )

    return refund_id


# =====================================================
# Run once (cron entry)
# =====================================================
def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)

        print("======================================")
        print("Robot #1 — Owner Silence (TEST MODE)")
        print("Window: 1 minute")
        print(f"Candidates found: {len(items)}")

        for bk in items:
            print(f"- Booking #{bk.id}")
            rid = execute_one(db, bk)
            if rid:
                print(f"  ✅ refunded (refund_id={rid})")
            else:
                print("  ⏭️ skipped")

        print("Robot finished.")
        print("======================================")

    except Exception as e:
        print("❌ Robot error:", str(e))
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_once()
