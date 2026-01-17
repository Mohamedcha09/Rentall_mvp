# app/deposit_renter_silence_robot.py

"""
Robot #2 — Renter Silence after MD Open Window
=============================================
TEST MODE — 1 MINUTE

Behavior:
- MD opened window
- Renter did NOT respond within window
- Finalize MD decision
- Refund remaining deposit to renter (PayPal)
- CREATE owner compensation task for admin (ALWAYS)
- NEVER crash (like Robot #1)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog, User
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification, notify_admins
from sqlalchemy import or_


# =====================================================
WINDOW_DELTA = timedelta(minutes=1)   # test
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

    rows = db.query(Booking).filter(
        Booking.deposit_amount > 0,

        Booking.renter_24h_window_opened_at.isnot(None),
        Booking.renter_responded_at.is_(None),

        Booking.dm_decision_amount.isnot(None),
        Booking.dm_decision_final == False,

        Booking.payment_method == "paypal",

        # ✅ IMPORTANT FIX
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

    # -------------------------------------------------
    # 1) Refund renter (SAFE — NEVER crash)
    # -------------------------------------------------
    refund_amount = compute_refund_amount(bk)
    refund_id = None
    refund_error = None

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
    # 2) Finalize MD decision (ALWAYS)
    # -------------------------------------------------
    bk.dm_decision_final = True
    bk.dm_decision_at = now
    bk.deposit_status = "partially_withheld"
    bk.auto_finalized_by_robot = True

    # -------------------------------------------------
    # 3) Audit logs (ALWAYS)
    # -------------------------------------------------
    actor_id = get_system_actor_id(db)

    db.add(
        DepositAuditLog(
            booking_id=bk.id,
            actor_id=actor_id,
            actor_role="system",
            action="auto_finalize_md_renter_silent",
            amount=int(refund_amount),
            reason="Renter did not respond — decision finalized",
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
    # 4) Notifications (ALWAYS)
    # -------------------------------------------------
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
            body=f"Booking #{bk.id}: compensate owner {int(owner_amount)} CAD.",
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
        print("Robot #2 — Renter Silence (TEST MODE)")
        print("Window = 1 minute")
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
