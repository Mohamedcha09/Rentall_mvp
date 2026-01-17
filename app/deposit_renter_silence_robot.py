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

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog, User, DepositEvidence
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification, notify_admins
from sqlalchemy import exists, select


# ✅ test mode
WINDOW_DELTA = timedelta(minutes=1)     # 🔁 production: timedelta(hours=24)
NOW = lambda: datetime.now(timezone.utc)


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

    evidence_exists = (
        select(1)
        .where(DepositEvidence.booking_id == Booking.id)
        .exists()
    )

    rows = db.query(Booking).filter(
        Booking.deposit_amount > 0,

        Booking.renter_24h_window_opened_at.isnot(None),

        # ❌ renter did NOT reply
        Booking.renter_responded_at.is_(None),

        # ❌ renter did NOT upload any evidence  ✅ FIXED
        ~evidence_exists,

        Booking.dm_decision_amount.isnot(None),
        Booking.dm_decision_final == False,

        Booking.payment_method == "paypal",
        Booking.deposit_capture_id.isnot(None),
    ).all()

    valid: List[Booking] = []

    for bk in rows:
        opened_at = bk.renter_24h_window_opened_at
        if opened_at is None:
            continue

        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        if opened_at <= deadline:
            valid.append(bk)

    return valid


def compute_refund_amount(bk: Booking) -> float:
    try:
        return max(
            float(bk.deposit_amount or 0) - float(bk.dm_decision_amount or 0),
            0.0,
        )
    except Exception:
        return 0.0


def execute_one(db: Session, bk: Booking) -> Optional[str]:
    now = NOW()

    refund_amount = compute_refund_amount(bk)
    refund_id = None
    refund_error = None

    # 1) Refund renter (SAFE)
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

    # 2) Finalize decision
    bk.dm_decision_final = True
    bk.dm_decision_at = now
    bk.deposit_status = "partially_withheld"
    bk.auto_finalized_by_robot = True

    # 3) Audit logs
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

    # 4) Notifications
    try:
        push_notification(
            user_id=bk.renter_id,
            title="Deposit finalized ✅",
            body=f"No response/evidence received. Refunded: {refund_amount} CAD.",
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
