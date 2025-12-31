# app/deposit_owner_silence_robot.py
"""
Robot #1 — Owner Silence (After Return)
======================================
TEST MODE — 1 MINUTE

Behavior:
- Item returned OR return marked no problem
- Owner did NOT open dispute within window
- Auto refund FULL deposit via PayPal
- 💰 Refund is paid FROM PLATFORM AVAILABLE BALANCE
- Send notifications to renter & owner
- Log audit safely
- ✅ CLOSE DEPOSIT CASE
- ✅ CLOSE BOOKING
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import SessionLocal
from app.models import Booking, DepositAuditLog
from app.pay_api import send_deposit_refund
from app.notifications_api import push_notification

# 🔥 PLATFORM WALLET (NEW LOGIC)
from app.platform_wallet import spend_available, refund_revert


# =====================================================
# SYSTEM ACTOR (for audit logs)
# =====================================================
SYSTEM_ACTOR_ID = 0


# =====================================================
# ⏱️ TEST WINDOW — 1 MINUTE
# =====================================================
WINDOW_DELTA = timedelta(minutes=1)
NOW = lambda: datetime.now(timezone.utc)


# =====================================================
# Find eligible bookings
# =====================================================
def find_candidates(db: Session) -> List[Booking]:
    deadline = NOW() - WINDOW_DELTA

    return (
        db.query(Booking)
        .filter(
            Booking.deposit_amount > 0,
            Booking.deposit_refund_sent == False,

            # Item returned OR no-problem return
            or_(
                Booking.returned_at.isnot(None),
                and_(
                    Booking.return_check_no_problem == True,
                    Booking.return_check_submitted_at.isnot(None),
                ),
            ),

            # Owner did not open dispute
            Booking.owner_dispute_opened_at.is_(None),

            # Enough time passed
            or_(
                Booking.returned_at <= deadline,
                Booking.return_check_submitted_at <= deadline,
            ),

            # Avoid conflicting states
            or_(
                Booking.deposit_status.is_(None),
                ~Booking.deposit_status.in_(["in_dispute", "awaiting_renter"]),
            ),

            # PayPal only
            Booking.payment_method == "paypal",
            Booking.payment_provider.isnot(None),
        )
        .all()
    )


# =====================================================
# Compute refund amount
# =====================================================
def compute_refund_amount(bk: Booking) -> float:
    try:
        return float(bk.deposit_amount or 0)
    except Exception:
        return 0.0


# =====================================================
# Execute one booking
# =====================================================
def execute_one(db: Session, bk: Booking) -> Optional[str]:
    refund_amount = compute_refund_amount(bk)
    if refund_amount <= 0:
        return None

    capture_id = (bk.payment_provider or "").strip()

    # Safety: avoid invalid PayPal capture IDs
    if not capture_id or capture_id.lower() in ("paypal", "sandbox"):
        print(f"⏭️ Skip booking #{bk.id} (invalid capture_id={capture_id})")
        return None

    now = NOW()
    refund_id = None

    # =================================================
    # 💰 STEP 1 — DEDUCT FROM PLATFORM BALANCE
    # =================================================
    try:
        spend_available(
            db,
            amount=refund_amount,
            source="robot",
            booking_id=bk.id,
            note="Auto refund (owner silent) — platform balance used",
        )
    except Exception as e:
        print(f"❌ Not enough platform balance for booking #{bk.id}: {e}")
        db.rollback()
        return None

    # =================================================
    # 💳 STEP 2 — PAYPAL REFUND
    # =================================================
    try:
        refund_id = send_deposit_refund(
            db=db,
            booking=bk,
            amount=refund_amount,
        )
    except Exception as e:
        # 🔁 PayPal failed → revert platform balance
        try:
            refund_revert(
                db,
                amount=refund_amount,
                source="robot",
                booking_id=bk.id,
                note=f"PayPal refund failed, revert platform balance: {str(e)[:200]}",
            )
        except Exception:
            pass

        db.commit()
        print(f"❌ PayPal refund failed for booking #{bk.id}: {e}")
        return None

    # =================================================
    # ✅ STEP 3 — UPDATE BOOKING STATE (CLOSE EVERYTHING)
    # =================================================
    bk.deposit_refund_sent = True
    bk.deposit_refund_sent_at = now
    bk.deposit_refund_amount = refund_amount

    bk.deposit_status = "refunded"
    bk.deposit_case_closed = True
    bk.auto_finalized_by_robot = True

    # 🔒 Close booking
    bk.status = "closed"

    # =================================================
    # 🧾 Audit log
    # =================================================
    db.add(
        DepositAuditLog(
            booking_id=bk.id,
            actor_id=SYSTEM_ACTOR_ID,
            actor_role="system",
            action="auto_refund_owner_silent",
            amount=int(refund_amount),
            reason="Owner did not open dispute within allowed window",
            details=f"refund_id={refund_id}",
        )
    )

    db.commit()

    # =================================================
    # 🔔 Notifications
    # =================================================
    try:
        push_notification(
            user_id=bk.renter_id,
            title="Deposit refunded ✅",
            body="Your deposit has been fully refunded automatically.",
            data={"booking_id": bk.id},
        )
    except Exception:
        pass

    try:
        push_notification(
            user_id=bk.owner_id,
            title="Deposit released",
            body="The deposit was automatically refunded because no dispute was opened.",
            data={"booking_id": bk.id},
        )
    except Exception:
        pass

    return refund_id


# =====================================================
# Run once (cron entry)
# =====================================================
def run_once():
    db = SessionLocal()
    try:
        items = find_candidates(db)

        print("======================================")
        print("Robot #1 — Owner Silence (TEST MODE)")
        print("Window: 1 minute")
        print(f"Candidates found: {len(items)}")

        for bk in items:
            print(f"- Booking #{bk.id}")
            rid = execute_one(db, bk)
            if rid:
                print(f"  ✅ refunded & closed (refund_id={rid})")
            else:
                print("  ⏭️ skipped")

        print("Robot finished successfully.")
        print("======================================")

    except Exception as e:
        print("❌ Robot error:", str(e))
        raise
    finally:
        db.close()


# =====================================================
# CLI
# =====================================================
if __name__ == "__main__":
    run_once()