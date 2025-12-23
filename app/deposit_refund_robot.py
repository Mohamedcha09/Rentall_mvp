# app/deposit_refund_robot.py
"""
Deposit Refund Robot
--------------------
الروبوت مسؤول فقط عن:
- اختيار الحجوزات الجاهزة
- حساب مبلغ إرجاع الديبو للزبون
- تسجيل القرار في DB (PLAN فقط)
❌ لا يرسل أموال
❌ لا يلمس تعويض المالك
"""

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog


# =========================================================
# المرحلة 2 — اختيار الحجوزات الجاهزة
# =========================================================

def find_candidates(db: Session):
    return db.query(Booking).filter(
        Booking.deposit_amount > 0,
        Booking.deposit_refund_sent == False,
        or_(
            # A) بعد قرار DM
            Booking.dm_decision_at.isnot(None),

            # B) انتهى بدون مشاكل
            and_(
                Booking.return_check_no_problem == True,
                Booking.return_check_submitted_at.isnot(None)
            )
        )
    ).all()


# =========================================================
# المرحلة 3 — حساب مبلغ الإرجاع
# =========================================================

def compute_refund_amount(booking: Booking) -> float:
    """
    يحسب كم يرجع للزبون
    """

    deposit = float(booking.deposit_amount or 0)

    # A) بعد قرار DM
    if booking.dm_decision_at:
        dm_amount = float(booking.dm_decision_amount or 0)
        refund = deposit - dm_amount
        return max(refund, 0)

    # B) بدون مشاكل
    if booking.return_check_no_problem:
        return deposit

    return 0


# =========================================================
# المرحلة 3 — تسجيل الخطة (بدون إرسال)
# =========================================================

def apply_refund_plan(db: Session, booking: Booking, refund_amount: float):
    """
    يكتب الخطة فقط:
    - deposit_refund_amount
    - Audit log
    """

    booking.deposit_refund_amount = refund_amount

    db.add(DepositAuditLog(
        booking_id=booking.id,
        actor_id=booking.owner_id,  # روبوت = system (نغيّره لاحقًا)
        actor_role="system",
        action="robot_refund_planned",
        amount=int(refund_amount),
        reason="Automatic refund plan by robot"
    ))

    db.commit()


# =========================================================
# المرحلة 1 + 3 — تشغيل الروبوت
# =========================================================

def run_once():
    db = SessionLocal()
    try:
        bookings = find_candidates(db)

        print("======================================")
        print("Deposit Refund Robot — PLAN MODE")
        print(f"Candidates: {len(bookings)}")

        for b in bookings:
            refund = compute_refund_amount(b)

            apply_refund_plan(db, b, refund)

            print(
                f"- Booking #{b.id} | deposit={b.deposit_amount} | "
                f"refund_planned={refund}"
            )

        print("======================================")

    finally:
        db.close()


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    run_once()
