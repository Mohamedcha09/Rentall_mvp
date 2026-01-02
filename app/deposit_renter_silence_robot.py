# app/deposit_renter_silence_robot.py
"""
Robot #3 — Renter Silence after MD Open Window
=============================================
FINAL VERSION — PAYPAL SAFE (LIKE ROBOT #1)

Behavior:
- MD opened window
- Renter did NOT respond within window
- Finalize MD decision ONLY AFTER successful PayPal refund
- Refund remaining deposit to renter (PayPal)
- CREATE owner compensation task for admin (AFTER refund)
- Log everything
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
# ⏱️ TEST WINDOW — 1 MINUTE (CHANGE TO 24h IN PROD)
# =====================================================
WINDOW_DELTA = timedelta(minutes=1)
NOW = lambda: datetime.now(timezone.utc)


# =====================================================
# Find eligible bookings
# =====================================================
def find_candidates(db: Session) -> List[Booking]:
    deadline = NOW() - WINDOW_DELTA

    rows = db.query(Booking).filter(
        Booking.deposit_amount > 0,

        Booking.renter_24h_window_opened_at.isnot(None),
        Booking.renter_responded_at.is_(None),

        Booking.dm_decision_amount.isnot(None),
        Booking.dm_decision_final == False,

        Booking.payment_method == "paypal",
        Booking.payment_provider.isnot(None),
    ).all()

    valid: List[Booking] = []

    for bk in rows:
        opened_at = bk.renter_24h_window_opened_at
        if not opened_at:
            continue

        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        # ⛔ STRICT capture_id validation (LIKE ROBOT #1)
        capture_id = (bk.payment_provider or "").strip().lower()
        if not capture_id or capture_id in ("paypal", "sandbox"):
            continue

        if opened_at <= deadline:
            valid.append(bk)

    return valid


# =====================================================
# Compute refund amount
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
# Execute robot (STRICT MODE)
# =====================================================
def execute_one(db: Session, bk: Booking):
    now = NOW()

    refund_amount = compute_refund_amount(bk)
    if refund_amount <= 0:
        print(f"⏭️ Booking #{bk.id} — nothing to refund")
        return

    # =================================================
    # 🔒 PAYPAL REFUND FIRST (NO TRY / NO SILENT FAIL)
    # =================================================
    refund_id = send_deposit_refund(
        db=db,
        booking=bk,
        amount=refund_amount,
    )

    # =================================================
    # ✅ ONLY AFTER SUCCESSFUL REFUND
    # =================================================
    bk.deposit_refund_sent = True
    bk.deposit_refund_sent_at = now
    bk.deposit_refund_amount = refund_amount

    bk.dm_decision_final = True
    bk.dm_decision_at = now
    bk.deposit_status = "partially_withheld"
    bk.auto_finalized_by_robot = True

    # =================================================
    # Audit logs (TRUTHFUL)
    # =================================================
    admin = db.query(User).filter(User.role == "admin").first()
    if admin:
        # Renter refund log
        db.add(
            DepositAuditLog(
                booking_id=bk.id,
                actor_id=admin.id,
                actor_role="system",
                action="auto_finalize_md_renter_silent",
                amount=int(refund_amount),
                reason="Renter did not respond — refund succeeded",
                details=f"refund_id={refund_id}",
            )
        )

        # 🔥 OWNER COMPENSATION TASK (AFTER REFUND)
        owner_amount = int(bk.dm_decision_amount or 0)
        if owner_amount > 0:
            db.add(
                DepositAuditLog(
                    booking_id=bk.id,
                    actor_id=admin.id,
                    actor_role="system",
                    action="owner_compensation_required",
                    amount=owner_amount,
                    reason="Owner compensation required after renter silence",
                    details="manual payout required",
                )
            )

    db.commit()

    # =================================================
    # Notifications
    # =================================================
    try:
        push_notification(
            user_id=bk.renter_id,
            title="Deposit finalized ✅",
            body=f"Your deposit was finalized automatically. Refunded: {refund_amount} CAD.",
            data={"booking_id": bk.id},
        )
    except Exception:
        pass

    try:
        notify_admins(
            title="Owner compensation required",
            body=f"Booking #{bk.id}: compensate owner {int(bk.dm_decision_amount or 0)} CAD.",
            data={"booking_id": bk.id},
        )
    except Exception:
        pass


# =====================================================
# Run once (cron entry)
# =====================================================
def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)

        print("======================================")
        print("Robot #3 — Renter Silence (STRICT MODE)")
        print("Window =", WINDOW_DELTA)
        print(f"Candidates found: {len(items)}")

        for bk in items:
            print(f"- Booking #{bk.id}")
            execute_one(db, bk)
            print("  ✅ refund + finalize done")

        print("Robot finished.")
        print("======================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_once()
