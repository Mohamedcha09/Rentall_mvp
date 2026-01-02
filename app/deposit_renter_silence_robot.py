# app/deposit_renter_silence_robot.py
"""
Robot #3 — Renter Silence after MD Open Window
=============================================
FINAL VERSION — SAME BEHAVIOR AS ROBOT #1

Behavior:
- Try PayPal refund first
- If refund fails → SKIP booking (NO CRASH, NO DB UPDATE)
- If refund succeeds → finalize decision
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
WINDOW_DELTA = timedelta(minutes=1)  # test
NOW = lambda: datetime.now(timezone.utc)
# =====================================================


def find_candidates(db: Session) -> List[Booking]:
    deadline = NOW() - WINDOW_DELTA

    rows = db.query(Booking).filter(
        Booking.deposit_amount > 0,
        Booking.deposit_refund_sent == False,

        Booking.renter_24h_window_opened_at.isnot(None),
        Booking.renter_responded_at.is_(None),

        Booking.dm_decision_amount.isnot(None),
        Booking.dm_decision_final == False,

        Booking.payment_method == "paypal",
        Booking.payment_provider.isnot(None),
    ).all()

    valid = []

    for bk in rows:
        opened_at = bk.renter_24h_window_opened_at
        if not opened_at:
            continue

        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        capture_id = (bk.payment_provider or "").strip().lower()
        if not capture_id or capture_id in ("paypal", "sandbox"):
            continue

        if opened_at <= deadline:
            valid.append(bk)

    return valid


def compute_refund_amount(bk: Booking) -> float:
    try:
        return max(
            float(bk.deposit_amount) - float(bk.dm_decision_amount or 0),
            0.0,
        )
    except Exception:
        return 0.0


def execute_one(db: Session, bk: Booking):
    now = NOW()

    refund_amount = compute_refund_amount(bk)
    if refund_amount <= 0:
        return

    # =================================================
    # 🔑 TRY REFUND — SAME LOGIC AS ROBOT #1
    # =================================================
    try:
        refund_id = send_deposit_refund(
            db=db,
            booking=bk,
            amount=refund_amount,
        )
    except Exception as e:
        print(f"⏭️ Skip booking #{bk.id} — PayPal refund failed: {e}")
        return  # 👈 VERY IMPORTANT (no crash)

    # =================================================
    # ✅ REFUND SUCCESS → UPDATE DB
    # =================================================
    bk.deposit_refund_sent = True
    bk.deposit_refund_sent_at = now
    bk.deposit_refund_amount = refund_amount

    bk.dm_decision_final = True
    bk.dm_decision_at = now
    bk.deposit_status = "partially_withheld"
    bk.auto_finalized_by_robot = True

    admin = db.query(User).filter(User.role == "admin").first()
    if admin:
        db.add(
            DepositAuditLog(
                booking_id=bk.id,
                actor_id=admin.id,
                actor_role="system",
                action="auto_finalize_md_renter_silent",
                amount=int(refund_amount),
                reason="Renter silent — refund succeeded",
                details=f"refund_id={refund_id}",
            )
        )

        owner_amount = int(bk.dm_decision_amount or 0)
        if owner_amount > 0:
            db.add(
                DepositAuditLog(
                    booking_id=bk.id,
                    actor_id=admin.id,
                    actor_role="system",
                    action="owner_compensation_required",
                    amount=owner_amount,
                    reason="Manual owner compensation required",
                    details="admin payout",
                )
            )

    db.commit()

    try:
        push_notification(
            user_id=bk.renter_id,
            title="Deposit finalized ✅",
            body=f"Refunded: {refund_amount} CAD.",
            data={"booking_id": bk.id},
        )
    except Exception:
        pass

    try:
        notify_admins(
            title="Owner compensation required",
            body=f"Booking #{bk.id} — compensate owner {int(bk.dm_decision_amount or 0)} CAD.",
            data={"booking_id": bk.id},
        )
    except Exception:
        pass


def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)
        print(f"Robot #3 candidates: {len(items)}")

        for bk in items:
            print(f"- Booking #{bk.id}")
            execute_one(db, bk)

    finally:
        db.close()


if __name__ == "__main__":
    run_once()
