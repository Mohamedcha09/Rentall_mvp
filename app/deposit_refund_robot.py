# app/deposit_refund_robot.py
"""
Deposit Refund Robot (TEST MODE)
================================
⏱️ TEST: 1 minute instead of 24 hours
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification


# =========================================================
# Helpers
# =========================================================

NOW = lambda: datetime.utcnow()
TEST_WINDOW = timedelta(minutes=1)  # 🔧 change to hours=24 later


# =========================================================
# 1️⃣ Auto refund if owner silent
# =========================================================

def auto_refund_owner_silent(db: Session):
    limit_time = NOW() - TEST_WINDOW

    bookings = db.query(Booking).filter(
        Booking.deposit_amount > 0,
        Booking.deposit_refund_sent == False,
        Booking.returned_at.isnot(None),
        Booking.owner_dispute_opened_at.is_(None),
        Booking.returned_at <= limit_time,
    ).all()

    for b in bookings:
        try:
            # 🔥 Refund money
            execute_refund(db, b, float(b.deposit_amount))

            b.auto_finalized_by_robot = True
            b.deposit_case_closed = True

            # 🧾 Audit log (SYSTEM → actor_id = None)
            db.add(DepositAuditLog(
                booking_id=b.id,
                actor_id=None,
                actor_role="system",
                action="auto_refund_owner_silent",
                amount=int(b.deposit_amount),
                reason="Owner did not open dispute within test window",
            ))

            # 🔔 Notify renter
            push_notification(
                db=db,
                user_id=b.renter_id,
                title="Deposit refunded ✅",
                body="The owner did not report any issue. Your deposit was fully refunded.",
                url=f"/bookings/{b.id}/deposit/summary",
                kind="deposit",
            )

            # 🔔 Notify owner
            push_notification(
                db=db,
                user_id=b.owner_id,
                title="Deposit automatically refunded",
                body="You did not open a dispute in time. The deposit was refunded.",
                url=f"/bookings/{b.id}/deposit/summary",
                kind="deposit",
            )

            db.commit()

        except Exception as e:
            db.rollback()
            print(f"❌ Error processing booking #{b.id}:", e)


# =========================================================
# 2️⃣ Auto finalize MD decision if renter silent
# =========================================================

def auto_finalize_md_decision(db: Session):
    limit_time = NOW() - TEST_WINDOW

    bookings = db.query(Booking).filter(
        Booking.renter_24h_window_opened_at.isnot(None),
        Booking.renter_responded_at.is_(None),
        Booking.dm_decision_final == False,
        Booking.renter_24h_window_opened_at <= limit_time,
    ).all()

    for b in bookings:
        try:
            b.dm_decision_final = True
            b.deposit_case_closed = True
            b.dm_decision_at = NOW()

            db.add(DepositAuditLog(
                booking_id=b.id,
                actor_id=None,
                actor_role="system",
                action="auto_finalize_md_decision",
                amount=int(b.dm_decision_amount or 0),
                reason="Renter did not respond within test window",
            ))

            db.commit()

        except Exception as e:
            db.rollback()
            print(f"❌ Error finalizing MD decision for booking #{b.id}:", e)


# =========================================================
# 3️⃣ Refund candidates
# =========================================================

def find_candidates(db: Session):
    return db.query(Booking).filter(
        Booking.deposit_amount > 0,
        Booking.deposit_refund_sent == False,
        or_(
            and_(
                Booking.dm_decision_final == True,
                Booking.dm_decision_at.isnot(None),
            ),
            and_(
                Booking.return_check_no_problem == True,
                Booking.return_check_submitted_at.isnot(None),
            ),
        ),
    ).all()


# =========================================================
# 4️⃣ Refund amount
# =========================================================

def compute_refund_amount(booking: Booking) -> float:
    deposit = float(booking.deposit_amount or 0)

    if booking.dm_decision_final:
        return max(deposit - float(booking.dm_decision_amount or 0), 0)

    if booking.return_check_no_problem:
        return deposit

    return 0.0


# =========================================================
# 5️⃣ Execute refund (PayPal)
# =========================================================

def execute_refund(db: Session, booking: Booking, refund_amount: float):
    if refund_amount <= 0:
        return

    if booking.payment_method != "paypal":
        return

    ref = send_deposit_refund(
        db=db,
        booking=booking,
        amount=refund_amount,
    )

    booking.deposit_refund_sent = True
    booking.deposit_refund_sent_at = NOW()
    booking.deposit_refund_amount = refund_amount

    db.add(DepositAuditLog(
        booking_id=booking.id,
        actor_id=None,
        actor_role="system",
        action="robot_refund_sent",
        amount=int(refund_amount),
        reason="Deposit refund executed by robot",
        details=f"ref={ref}",
    ))


# =========================================================
# 6️⃣ Run robot
# =========================================================

def run_once():
    db = SessionLocal()
    try:
        print("🤖 Deposit Refund Robot — TEST MODE (1 minute)")

        auto_refund_owner_silent(db)
        auto_finalize_md_decision(db)

        for b in find_candidates(db):
            try:
                refund = compute_refund_amount(b)
                execute_refund(db, b, refund)
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"❌ Refund error for booking #{b.id}:", e)

        print("✅ Robot finished successfully")

    finally:
        db.close()


if __name__ == "__main__":
    run_once()
