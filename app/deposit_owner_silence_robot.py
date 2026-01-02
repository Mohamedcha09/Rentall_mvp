# app/deposit_owner_silence_robot.py
"""
Robot #1 — Owner Silence (After Return)
======================================

FINAL VERSION — PAYPAL SAFE (NO DISPUTE ONLY)

Behavior:
- Item returned OR return marked no problem
- Wait WINDOW_DELTA
- If NO owner dispute opened during window → auto refund FULL deposit
- If owner dispute exists → SKIP forever (do NOT touch booking)
- NEVER interfere with MD / Robot #3 flow
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
# ⏱️ WINDOW (TEST = 1 MINUTE, PROD = 24H)
# =====================================================
WINDOW_DELTA = timedelta(minutes=1)
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
# 🔍 FIND ELIGIBLE BOOKINGS
# =====================================================
def find_candidates(db: Session) -> List[Booking]:
    deadline = NOW() - WINDOW_DELTA

    return (
        db.query(Booking)
        .filter(
            # ---- deposit exists and not refunded
            Booking.deposit_amount > 0,
            Booking.deposit_refund_sent == False,

            # ---- item returned
            or_(
                Booking.returned_at.isnot(None),
                and_(
                    Booking.return_check_no_problem == True,
                    Booking.return_check_submitted_at.isnot(None),
                ),
            ),

            # ---- 🚫 NO OWNER DISPUTE (CORE RULE)
            Booking.owner_dispute_opened_at.is_(None),

            # ---- 🔒 NEVER TOUCH ADMIN / MD FLOW
            # IMPORTANT: allow NULL OR 0 (some DBs store 0 by default)
            or_(Booking.dm_decision_amount.is_(None), Booking.dm_decision_amount == 0),
            Booking.renter_24h_window_opened_at.is_(None),

            # ---- ⏱️ window expired
            or_(
                Booking.returned_at <= deadline,
                Booking.return_check_submitted_at <= deadline,
            ),

            # ---- PayPal only
            Booking.payment_method == "paypal",

            # keep this; capture_id validity is checked again in execute_one
            Booking.payment_provider.isnot(None),
        )
        .all()
    )


# =====================================================
# 💰 COMPUTE REFUND
# =====================================================
def compute_refund_amount(bk: Booking) -> float:
    try:
        return float(bk.deposit_amount or 0)
    except Exception:
        return 0.0


# =====================================================
# ⚙️ EXECUTE ONE BOOKING
# =====================================================
def execute_one(db: Session, bk: Booking) -> Optional[str]:
    refund_amount = compute_refund_amount(bk)
    if refund_amount <= 0:
        return None

    capture_id = (bk.payment_provider or "").strip().lower()
    if not capture_id or capture_id in ("paypal", "sandbox"):
        print(f"⏭️ Skip booking #{bk.id} (invalid capture_id)")
        return None

    # ---- PayPal refund FIRST (safety)
    refund_id = send_deposit_refund(
        db=db,
        booking=bk,
        amount=refund_amount,
    )

    now = NOW()

    # ---- finalize booking
    bk.deposit_refund_sent = True
    bk.deposit_refund_sent_at = now
    bk.deposit_refund_amount = refund_amount
    bk.deposit_status = "refunded"
    bk.deposit_case_closed = True
    bk.auto_finalized_by_robot = True
    bk.status = "closed"

    # ---- audit log
    db.add(
        DepositAuditLog(
            booking_id=bk.id,
            actor_id=get_system_actor_id(db),
            actor_role="system",
            action="auto_refund_no_owner_dispute",
            amount=int(refund_amount),
            reason="Owner did not open dispute within allowed window",
            details=f"refund_id={refund_id}",
        )
    )

    db.commit()

    # ---- notify renter
    try:
        push_notification(
            user_id=bk.renter_id,
            title="Deposit refunded ✅",
            body="Your deposit has been refunded automatically.",
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
        print(f"Robot #1 candidates: {len(items)}")
        for bk in items:
            execute_one(db, bk)
    finally:
        db.close()


if __name__ == "__main__":
    run_once()
