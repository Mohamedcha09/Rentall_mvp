# app/deposit_renter_silence_robot.py

"""
Robot #2 — Renter Silence after MD Open Window
=============================================
TEST MODE — 1 MINUTE (change to 24h in prod)

Behavior:
- MD opened evidence window
- Renter did NOT respond
- Renter did NOT upload any evidence
- Finalize MD decision automatically
- Refund remaining deposit to renter (PayPal)
- Create owner compensation task (audit only)
- NEVER crash
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import exists

from app.database import SessionLocal
from app.models import (
    Booking,
    DepositAuditLog,
    User,
    DepositEvidence,   # ✅ IMPORTANT
)
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification, notify_admins


# =====================================================
WINDOW_DELTA = timedelta(minutes=1)   # 🔁 change to hours=24 in production
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


# =====================================================
# 🔍 FIND BOOKINGS WHERE RENTER IS SILENT
# =====================================================
def find_candidates(db: Session) -> List[Booking]:
    deadline = NOW() - WINDOW_DELTA

    rows = db.query(Booking).filter(
        # deposit exists
        Booking.deposit_amount > 0,

        # window opened
        Booking.renter_24h_window_opened_at.isnot(None),

        # ❌ renter did NOT reply
        Booking.renter_responded_at.is_(None),

        # ❌ renter did NOT upload any evidence
        ~exists().where(
            DepositEvidence.booking_id == Booking.id
        ),

        # DM decision exists but NOT final
        Booking.dm_decision_amount.isnot(None),
        Booking.dm_decision_final == False,

        # PayPal only
        Booking.payment_method == "paypal",
        Booking.deposit_capture_id.isnot(None),
    ).all()

    valid: List[Booking] = []

    for bk in rows:
        opened_at = bk.renter_24h_window_opened_at
        if not opened_at:
            continue

        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        if opened_at <= deadline:
            valid.append(bk)

    return valid


# =====================================================
# 💰 COMPUTE REFUND
# =====================================================
def compute_refund_amount(bk: Booking) -> float:
    try:
        return max(
            float(bk.deposit_amount or 0)
            - float(bk.dm_decision_amount or 0),
            0.0,
        )
    except Exception:
        return 0.0


# =====================================================
# ⚙️ EXECUTE ONE BOOKING
# =====================================================
def execute_one(db: Session, bk: Booking) -> Optional[str]:
    now = NOW()

    refund_amount = compute_refund_amount(bk)
    refund_id = None
    refund_error = None

    # -------------------------------------------------
    # 1) REAL PAYPAL REFUND (SAFE)
    # -------------------------------------------------
    if refund_amount > 0:
        try:
            refund_id = send_deposit_refund(
                db=db,
                booking=bk,
                amount=refund_amount,
            )

            bk.deposit_refund_sent = True
            bk.deposit_refund_sent_at = now
            bk.deposit_refund_amount = refund_amount

        except Exception as e:
            refund_error = str(e)
            print(f"⚠️ Refund failed for booking #{bk.id}: {refund_error}")

    # -------------------------------------------------
    # 2) FINALIZE DM DECISION
    # -------------------------------------------------
    bk.dm_decision_final = True
    bk.dm_decision_at = now
    bk.deposit_status = "partially_withheld"
    bk.auto_finalized_by_robot = True

    # -------------------------------------------------
    # 3) AUDIT LOGS
    # -------------------------------------------------
    actor_id = get_system_actor_id(db)

    db.add(
        DepositAuditLog(
            booking_id=bk.id,
            actor_id=actor_id,
            actor_role="system",
            action="auto_finalize_md_renter_silent",
            amount=int(refund_amount),
            reason="Renter did not respond and uploaded no evidence",
            details=(
                f"refund_id={refund_id}"
                if refund_id
                else f"refund_failed={refund_error}"
            ),
        )
    )

    owner_amount = float(bk.dm_decision_amount or 0)
    if owner_amount > 0:
        db.add(
            DepositAuditLog(
                booking_id=bk.id,
                actor_id=actor_id,
                actor_role="system",
                action="owner_compensation_required",
                amount=int(owner_amount),
                reason="Owner compensation required after renter silence",
                details="manual payout required",
            )
        )

    db.commit()

    # -------------------------------------------------
    # 4) NOTIFICATIONS
    # -------------------------------------------------
    try:
        push_notification(
            user_id=bk.renter_id,
            title="Deposit finalized ✅",
            body=(
                "You did not respond within the allowed time. "
                f"Refunded amount: {refund_amount} CAD."
            ),
            data={"booking_id": bk.id},
        )
    except Exception:
        pass

    try:
        notify_admins(
            title="Owner compensation required",
            body=f"Booking #{bk.id}: owner compensation {int(owner_amount)} CAD",
            data={"booking_id": bk.id},
        )
    except Exception:
        pass

    return refund_id


# =====================================================
# ▶️ RUN ONCE
# =====================================================
def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)

        print("======================================")
        print("Robot #2 — Renter Silence")
        print(f"Window = {WINDOW_DELTA}")
        print(f"Candidates found: {len(items)}")

        for bk in items:
            print(f"- Booking #{bk.id}")
            execute_one(db, bk)
            print("  ✅ processed")

        print("Robot finished.")
        print("======================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_once()
