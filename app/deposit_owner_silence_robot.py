# app/deposit_owner_silence_robot.py
"""
Robot #1 — Owner Silence (After Return)
======================================
TEST MODE — 1 MINUTE

Behavior:
- Item returned OR return marked no problem
- Owner did NOT open dispute within window
- Auto refund FULL deposit via PayPal
- Send notifications to renter & owner
- Log audit safely
- Close deposit case
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification


# =====================================================
# SYSTEM ACTOR (for audit logs)
# =====================================================
SYSTEM_ACTOR_ID = 0


# =====================================================
# ⏱️ TEST WINDOW — 1 MINUTE
# =====================================================
WINDOW_DELTA = timedelta(minutes=1)
NOW = lambda: datetime.now(timezone.utc)


# =====================================================
# Find eligible bookings
# =====================================================
def find_candidates(db: Session) -> List[Booking]:
    deadline = NOW() - WINDOW_DELTA

    return (
        db.query(Booking)
        .filter(
            Booking.deposit_amount > 0,
            Booking.deposit_refund_sent == False,

            # Item returned OR no-problem return
            or_(
                Booking.returned_at.isnot(None),
                and_(
                    Booking.return_check_no_problem == True,
                    Booking.return_check_submitted_at.isnot(None),
                ),
            ),

            # Owner did not open dispute
            Booking.owner_dispute_opened_at.is_(None),

            # Enough time passed
            or_(
                Booking.returned_at <= deadline,
                Booking.return_check_submitted_at <= deadline,
            ),

            # Avoid conflicting states
            or_(
                Booking.deposit_status.is_(None),
                ~Booking.deposit_status.in_(["in_dispute", "awaiting_renter"]),
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
# Execute one booking
# =====================================================
def execute_one(db: Session, bk: Booking) -> Optional[str]:
    refund_amount = compute_refund_amount(bk)
    if refund_amount <= 0:
        return None

    capture_id = (bk.payment_provider or "").strip()

    # Safety: avoid invalid PayPal capture IDs
    if not capture_id or capture_id.lower() in ("paypal", "sandbox"):
        print(f"⏭️ Skip booking #{bk.id} (invalid capture_id={capture_id})")
        return None

    # 🔥 PayPal refund
    refund_id = send_deposit_refund(
        db=db,
        booking=bk,
        amount=refund_amount,
    )

    now = NOW()

    # Update booking state
    bk.deposit_refund_sent = True
    bk.deposit_refund_sent_at = now
    bk.deposit_refund_amount = refund_amount
    bk.deposit_status = "refunded"
    bk.deposit_case_closed = True
    bk.auto_finalized_by_robot = True
    bk.status = "closed"

    # 🧾 Audit log (SAFE)
    try:
        db.add(
            DepositAuditLog(
                booking_id=bk.id,
                actor_id=SYSTEM_ACTOR_ID,
                actor_role="system",
                action="auto_refund_owner_silent",
                amount=int(refund_amount),
                reason="Owner did not open dispute within test window",
                details=f"refund_id={refund_id}",
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print("⚠️ Audit log failed but refund succeeded:", e)

    # 🔔 Notifications
    push_notification(
        user_id=bk.renter_id,
        title="Deposit refunded ✅",
        body="Your deposit has been fully refunded successfully.",
        data={"booking_id": bk.id},
    )

    push_notification(
        user_id=bk.owner_id,
        title="Deposit refunded to renter",
        body="The deposit was refunded automatically because no dispute was opened.",
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
