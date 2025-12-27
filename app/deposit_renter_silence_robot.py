"""
Robot #2 — Renter Silence after MD Open Window
=============================================
TEST MODE — 1 MINUTE

Behavior:
- MD opened 24h window (test = 1 minute)
- Renter did NOT respond
- Finalize MD decision
- Refund remaining deposit to renter (PayPal)
- Notify admins to compensate owner manually
- Log action
- Close deposit case
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog, User
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification, notify_admins


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

    bookings = db.query(Booking).filter(
        # Deposit exists
        Booking.deposit_amount > 0,

        # MD opened window
        Booking.renter_24h_window_opened_at.isnot(None),

        # Renter did NOT respond
        Booking.renter_responded_at.is_(None),

        # MD decision exists and NOT final
        Booking.dm_decision_amount.isnot(None),
        Booking.dm_decision_final == False,

        # PayPal only
        Booking.payment_method == "paypal",
        Booking.payment_provider.isnot(None),
    ).all()

    valid: List[Booking] = []

    for bk in bookings:
        opened_at = bk.renter_24h_window_opened_at
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        if opened_at <= deadline:
            # safety: valid capture id
            cap = (bk.payment_provider or "").strip().lower()
            if cap and cap not in ("paypal", "sandbox"):
                valid.append(bk)

    return valid


# =====================================================
# Compute refund amount (remaining to renter)
# =====================================================
def compute_refund_amount(bk: Booking) -> float:
    try:
        return max(
            float(bk.deposit_amount) - float(bk.dm_decision_amount or 0),
            0.0,
        )
    except Exception:
        return 0.0


# =====================================================
# Execute robot action
# =====================================================
def execute_one(db: Session, bk: Booking):
    now = NOW()

    # 1️⃣ Finalize MD decision
    bk.dm_decision_final = True
    bk.dm_decision_at = now
    bk.deposit_case_closed = True
    bk.deposit_status = "withhold_final"
    bk.status = "closed"
    bk.auto_finalized_by_robot = True

    # 2️⃣ Refund renter (remaining amount)
    refund_amount = compute_refund_amount(bk)
    refund_id = None

    if refund_amount > 0:
        refund_id = send_deposit_refund(
            db=db,
            booking=bk,
            amount=refund_amount,
        )

    bk.deposit_refund_sent = True
    bk.deposit_refund_sent_at = now
    bk.deposit_refund_amount = refund_amount

    # 3️⃣ Audit log (FK-safe)
    admin = db.query(User).filter(User.role == "admin").first()
    if admin:
        db.add(
            DepositAuditLog(
                booking_id=bk.id,
                actor_id=admin.id,
                actor_role="system",
                action="auto_finalize_md_decision_renter_silent",
                amount=int(refund_amount),
                reason="Renter did not respond within test window",
                details=f"refund_id={refund_id}",
            )
        )

    db.commit()

    # 4️⃣ Notifications
    push_notification(
        user_id=bk.renter_id,
        title="Deposit finalized ✅",
        message=f"Your deposit was finalized automatically. Refunded: {refund_amount} CAD.",
        data={"booking_id": bk.id},
    )

    notify_admins(
        title="Owner compensation required",
        message=f"Booking #{bk.id}: compensate owner {bk.dm_decision_amount} CAD.",
        data={"booking_id": bk.id},
    )


# =====================================================
# Run once (cron entry)
# =====================================================
def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)

        print("======================================")
        print("Robot #2 — Renter Silence (TEST MODE)")
        print("Window = 1 minute")
        print(f"Candidates found: {len(items)}")

        for bk in items:
            print(f"- Booking #{bk.id}")
            execute_one(db, bk)
            print("  ✅ executed")

        print("Robot finished.")
        print("======================================")

    except Exception as e:
        print("❌ Robot error:", str(e))
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_once()
