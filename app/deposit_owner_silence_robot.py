# app/deposit_owner_silence_robot.py
"""
Robot #1 — Owner Silence (After Return)
======================================
TEST MODE — 1 MINUTE

Behavior:
- Item returned OR return marked no problem
- Owner did NOT open dispute within window
- Auto refund FULL deposit via PayPal
- Close dispute rights permanently
- Send notifications
- Log audit safely
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


SYSTEM_ACTOR_ID = 0
WINDOW_DELTA = timedelta(minutes=1)
NOW = lambda: datetime.now(timezone.utc)


def find_candidates(db: Session) -> List[Booking]:
    deadline = NOW() - WINDOW_DELTA

    return (
        db.query(Booking)
        .filter(
            Booking.deposit_amount > 0,
            Booking.deposit_refund_sent == False,

            or_(
                Booking.returned_at.isnot(None),
                and_(
                    Booking.return_check_no_problem == True,
                    Booking.return_check_submitted_at.isnot(None),
                ),
            ),

            Booking.owner_dispute_opened_at.is_(None),

            or_(
                Booking.returned_at <= deadline,
                Booking.return_check_submitted_at <= deadline,
            ),

            or_(
                Booking.deposit_status.is_(None),
                ~Booking.deposit_status.in_(["in_dispute", "awaiting_renter"]),
            ),

            Booking.payment_method == "paypal",
            Booking.payment_provider.isnot(None),
        )
        .all()
    )


def execute_one(db: Session, bk: Booking) -> Optional[str]:
    refund_amount = float(bk.deposit_amount or 0)
    if refund_amount <= 0:
        return None

    capture_id = (bk.payment_provider or "").strip()
    if not capture_id or capture_id.lower() in ("paypal", "sandbox"):
        print(f"⏭️ Skip booking #{bk.id} (invalid capture_id)")
        return None

    refund_id = send_deposit_refund(
        db=db,
        booking=bk,
        amount=refund_amount,
    )

    now = NOW()

    # ✅ FINAL STATE — THIS IS THE FIX
    bk.deposit_refund_sent = True
    bk.deposit_refund_sent_at = now
    bk.deposit_refund_amount = refund_amount
    bk.deposit_status = "refunded"
    bk.deposit_case_closed = True
    bk.owner_dispute_deadline_at = now   # 🔒 CLOSE DISPUTE WINDOW
    bk.status = "closed"
    bk.auto_finalized_by_robot = True

    try:
        db.add(
            DepositAuditLog(
                booking_id=bk.id,
                actor_id=SYSTEM_ACTOR_ID,
                actor_role="system",
                action="auto_refund_owner_silent",
                amount=int(refund_amount),
                reason="Owner did not open dispute within allowed window",
                details=f"refund_id={refund_id}",
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print("⚠️ Audit log failed:", e)

    push_notification(
        user_id=bk.renter_id,
        title="Deposit refunded ✅",
        body="Your deposit has been fully refunded automatically.",
        data={"booking_id": bk.id},
    )

    push_notification(
        user_id=bk.owner_id,
        title="Dispute window closed",
        body="The deposit was refunded automatically. The dispute window is now closed.",
        data={"booking_id": bk.id},
    )

    return refund_id


def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)

        print("======================================")
        print("Robot #1 — Owner Silence (FIXED)")
        print("Window: 1 minute")
        print(f"Candidates found: {len(items)}")

        for bk in items:
            print(f"- Booking #{bk.id}")
            rid = execute_one(db, bk)
            print("  ✅ executed" if rid else "  ⏭️ skipped")

        print("Robot finished.")
        print("======================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_once()
