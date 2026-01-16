# app/deposit_owner_silence_robot.py
"""
Robot #1 — Owner Silence (After Return)
======================================

FINAL VERSION — PAYPAL SAFE

Behavior:
- Item returned OR return marked no problem
- Owner did NOT open dispute within window
- Auto refund FULL deposit via PayPal
- Refund is ALWAYS done from original PayPal transaction
- Close deposit case
- Close booking
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog, User
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification


# =====================================================
WINDOW_DELTA = timedelta(days=3)
NOW = lambda: datetime.now(timezone.utc)
# =====================================================


def get_system_actor_id(db: Session) -> int:
    admin = (
        db.query(User)
        .filter(User.role == "admin")
        .order_by(User.id.asc())
        .first()
    )
    if not admin:
        raise RuntimeError("No admin user found")
    return admin.id


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


def execute_one(db: Session, bk: Booking) -> Optional[str]:
    refund_amount = compute_refund_amount(bk)
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

    bk.deposit_refund_sent = True
    bk.deposit_refund_sent_at = now
    bk.deposit_refund_amount = refund_amount
    bk.deposit_status = "refunded"
    bk.deposit_case_closed = True
    bk.auto_finalized_by_robot = True
    bk.status = "closed"

    db.add(
        DepositAuditLog(
            booking_id=bk.id,
            actor_id=get_system_actor_id(db),
            actor_role="system",
            action="auto_refund_owner_silent",
            amount=int(refund_amount),
            reason="Owner did not open dispute",
            details=f"refund_id={refund_id}",
        )
    )

    db.commit()

    try:
        push_notification(
            user_id=bk.renter_id,
            title="Deposit refunded ✅",
            body="Your deposit has been refunded.",
            data={"booking_id": bk.id},
        )
    except Exception:
        pass

    return refund_id


def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)
        print(f"Candidates: {len(items)}")
        for bk in items:
            execute_one(db, bk)
    finally:
        db.close()


if __name__ == "__main__":
    run_once()