# app/deposit_renter_silence_robot.py
"""
Robot #2 — Renter Silence after MD Open Window
=============================================
TEST MODE ONLY

- Cron runs every 1 minute
- Waiting window = 1 minute (HARDCODED)
- If renter did NOT respond
- Finalize MD decision
- Refund remaining deposit to renter
- Notify admin for owner compensation
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog, User
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification, notify_admins


# =====================================================
# ⏱️ HARD CODED WINDOW = 1 MINUTE
# =====================================================
WINDOW_DELTA = timedelta(minutes=1)
NOW = lambda: datetime.now(timezone.utc)


# =====================================================
# Find candidates
# =====================================================
def find_candidates(db: Session) -> List[Booking]:
    deadline = NOW() - WINDOW_DELTA

    items = (
        db.query(Booking)
        .filter(
            Booking.deposit_amount > 0,
            Booking.deposit_refund_sent == False,

            # MD opened window
            Booking.deposit_status == "awaiting_renter",

            # renter silent
            Booking.renter_responded_at.is_(None),

            # MD decision exists and not final
            Booking.dm_decision_amount.isnot(None),
            Booking.dm_decision_final == False,

            # PayPal only
            Booking.payment_method == "paypal",
            Booking.payment_provider.isnot(None),
        )
        .all()
    )

    out: List[Booking] = []
    for bk in items:
        # valid capture id
        cap = (bk.payment_provider or "").strip().lower()
        if not cap or cap in ("paypal", "sandbox"):
            continue

        opened_at = bk.renter_24h_window_opened_at
        if not opened_at:
            continue

        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        if opened_at <= deadline:
            out.append(bk)

    return out


# =====================================================
# Compute refund
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
# Execute
# =====================================================
def execute_one(db: Session, bk: Booking):
    now = NOW()

    # 1️⃣ Finalize decision
    bk.dm_decision_final = True
    bk.dm_decision_at = now
    bk.deposit_case_closed = True
    bk.deposit_status = "withhold_final"
    bk.status = "closed"
    bk.auto_finalized_by_robot = True

    # 2️⃣ Refund renter
    refund_amount = compute_refund_amount(bk)
    refund_id = None
    if refund_amount > 0:
        refund_id = send_deposit_refund(
            db=db,
            booking=bk,
            amount=refund_amount,
        )

    # 3️⃣ Audit log (SAFE)
    try:
        admin = db.query(User).filter(User.role == "admin").first()
        if admin:
            db.add(
                DepositAuditLog(
                    booking_id=bk.id,
                    actor_id=admin.id,
                    actor_role="system",
                    action="auto_finalize_md_decision_renter_silent",
                    amount=int(refund_amount),
                    reason="Renter silent after 1 minute test window",
                    details=f"refund_id={refund_id}",
                )
            )
    except Exception:
        pass

    db.commit()

    # 4️⃣ Notifications
    try:
        push_notification(
            user_id=bk.renter_id,
            title="Deposit updated ✅",
            message=f"Your deposit was finalized automatically. Refunded: {refund_amount}.",
            data={"booking_id": bk.id},
        )

        notify_admins(
            title="Owner compensation required",
            message=f"Booking #{bk.id}: owner compensation = {bk.dm_decision_amount}.",
            data={"booking_id": bk.id},
        )
    except Exception:
        pass


# =====================================================
# Run once
# =====================================================
def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)

        print("======================================")
        print("Robot #2 — Renter Silence (TEST)")
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
