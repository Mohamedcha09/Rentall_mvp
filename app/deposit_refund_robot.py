# app/deposit_refund_robot.py
"""
Deposit Refund Robot
====================
الروبوت مسؤول فقط عن:
- اختيار الحجوزات الجاهزة
- حساب مبلغ إرجاع الديبو للزبون
- إرسال Refund حقيقي عبر PayPal
- تحديث أعمدة refund في bookings

❌ لا يلمس تعويض المالك
❌ لا يلمس Stripe / Cash
"""

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog
from app.pay_api import send_deposit_refund


# =========================================================
# اختيار الحجوزات الجاهزة
# =========================================================

def find_candidates(db: Session):
    """
    نختار فقط الحجوزات التي:
    - عندها deposit
    - لم يتم refund بعد
    - إمّا:
        A) قرار DM موجود
        B) انتهت بدون مشاكل
    """
    return db.query(Booking).filter(
        Booking.deposit_amount > 0,
        Booking.deposit_refund_sent == False,
        or_(
            # A) بعد قرار DM
            Booking.dm_decision_at.isnot(None),

            # B) انتهى بدون مشاكل
            and_(
                Booking.return_check_no_problem == True,
                Booking.return_check_submitted_at.isnot(None),
            ),
        ),
    ).all()


# =========================================================
# حساب مبلغ الإرجاع
# =========================================================

def compute_refund_amount(booking: Booking) -> float:
    deposit = float(booking.deposit_amount or 0)

    # A) بعد قرار DM
    if booking.dm_decision_at:
        dm_amount = float(booking.dm_decision_amount or 0)
        refund = deposit - dm_amount
        return max(refund, 0)

    # B) بدون مشاكل
    if booking.return_check_no_problem:
        return deposit

    return 0.0


# =========================================================
# تنفيذ Refund حقيقي + تسجيل Log
# =========================================================

def execute_refund(db: Session, booking: Booking, refund_amount: float):
    """
    - يرسل Refund حقيقي عبر PayPal
    - يتجاهل أي حجز غير صالح
    """

    if refund_amount <= 0:
        return

    # =====================================================
    # 🔒 فلاتر أمان — لا نلمس إلا PayPal مع capture_id حقيقي
    # =====================================================

    if booking.payment_method != "paypal":
        print(f"⏭️ Skip booking #{booking.id} (not PayPal)")
        return

    capture_id = booking.payment_provider
    if not capture_id or capture_id.lower() == "paypal":
        print(f"⏭️ Skip booking #{booking.id} (missing PayPal capture_id)")
        return

    # =====================================================
    # 🔥 إرسال المال فعليًا
    # =====================================================

    refund_reference = send_deposit_refund(
        db=db,
        booking=booking,
        amount=refund_amount,
    )

    # =====================================================
    # 🧾 Audit Log
    # =====================================================

    db.add(
        DepositAuditLog(
            booking_id=booking.id,
            actor_id= 0,
            actor_role="system",
            action="robot_refund_sent",
            amount=int(refund_amount),
            reason="Automatic deposit refund executed by robot",
            details=f"refund_reference={refund_reference}",
        )
    )

    db.commit()


# =========================================================
# تشغيل الروبوت مرة واحدة
# =========================================================

def run_once():
    db = SessionLocal()
    try:
        bookings = find_candidates(db)

        print("======================================")
        print("Deposit Refund Robot — LIVE MODE")
        print(f"Candidates found: {len(bookings)}")

        for b in bookings:
            refund = compute_refund_amount(b)

            print(
                f"Booking #{b.id} | "
                f"deposit={b.deposit_amount} | "
                f"refund={refund}"
            )

            execute_refund(db, b, refund)

        print("Robot finished successfully.")
        print("======================================")

    except Exception as e:
        print("❌ Robot error:", str(e))
        raise

    finally:
        db.close()


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    run_once()